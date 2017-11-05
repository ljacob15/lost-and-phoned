"""Handles SMS messages to and from users."""

import os
import flask
import requests

from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery

import sql

# This variable specifies the name of a file that contains the OAuth 2.0
# information for this application, including its client_id and client_secret.
CLIENT_SECRETS_FILE = "client_secret.json"

# This OAuth 2.0 access scope allows for full read/write access to the
# authenticated user's account and requires requests to use an SSL connection.
SCOPES = ['https://www.googleapis.com/auth/contacts.readonly']
API_SERVICE_NAME = 'people'
API_VERSION = 'v1'

app = flask.Flask(__name__)
# Note: A secret key is included in the sample so that it works.
# If you use this code in your application, replace this with a truly secret
# key. See http://flask.pocoo.org/docs/0.12/quickstart/#sessions.
app.secret_key = 'REPLACE ME - this value is here as a placeholder.'


@app.route('/')
def index():
    """Display testing page."""

    return print_index_table()

@app.route("/twilio", methods=['GET', 'POST'])
def message_received():
    """Reply to a user via SMS."""
    #from_number = flask.request.values.get('From', None)
    #print(from_number)
	# Check if from_number is already in the database
    # If not, add them and get contacts from them
    #userMsg = client.messages()
    #number = request.form['From']
    message_body = flask.request.form['Body']
    words = message_body.split(" ")
    number = words[0]

    connection = sql.connect()

    if sql.process(str(number), connection):
        if 'credentials' not in flask.session:
            return flask.redirect('authorize')

        # Load credentials from the session.
        credentials = google.oauth2.credentials.Credentials(
            **flask.session['credentials'])

        people = googleapiclient.discovery.build(
            API_SERVICE_NAME, API_VERSION, credentials=credentials)

        # Save credentials back to session in case access token was refreshed.
        # ACTION ITEM: In a production app, you likely want to save these
        #              credentials in a persistent database instead.
        flask.session['credentials'] = credentials_to_dict(credentials)

        results = people.people().connections().list(
            resourceName='people/me',
            **{"requestMask_includeField": (
               "person.phoneNumbers,person.names")}).execute()

        #words = split(message_body)
        print(words)
        if len(words) == 3:
            query = str(words[1]) + " " + str(words[2])
        else:
            query = str(words[1])

        total = results['totalPeople']

        for i in range(0, total):
            name = results['connections'][i]
            if query == name['names'][0]['displayName']:
                phone = results['connections'][i]
                number = phone['phoneNumbers'][0]['value']
                break
        phone_number = number
        print(phone_number)
        resp = MessagingResponse()
        resp.message(str(phone_number))
        return str(resp)

    else: # New user
        resp = MessagingResponse()
        message = ("Welcome to Lost in Phone!"
                   "Please click the link below to get started: "
                   " http://cffabc37.ngrok.io/authorize")
        resp.message(message)

        sql.add_user(number, connection)

    return str(resp)


@app.route('/test')
def test_api_request():
    """Authentication success page."""

    return "Authentication success!"


@app.route('/authorize')
def authorize():
    """Authorization link."""

    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)

    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server apps.
        access_type='offline',
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes='true')

    # Store the state so the callback can verify the auth server response.
    flask.session['state'] = state

    return flask.redirect(authorization_url)


@app.route('/oauth2callback')
def oauth2callback():
    """Obtain credentials."""

    # Specify the state when creating the flow in the callback so that it can
    # verified in the authorization server response.
    state = flask.session['state']

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    authorization_response = flask.request.url
    flow.fetch_token(authorization_response=authorization_response)

    # Store credentials in the session.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    credentials = flow.credentials
    flask.session['credentials'] = credentials_to_dict(credentials)
    print(credentials)
    return flask.redirect(flask.url_for('test_api_request'))


@app.route('/revoke')
def revoke():
    """Revoke credentials."""

    if 'credentials' not in flask.session:
        return ('You need to <a href="/authorize">authorize</a> before ' +
                'testing the code to revoke credentials.')

    credentials = google.oauth2.credentials.Credentials(
        **flask.session['credentials'])

    response = requests.post('https://accounts.google.com/o/oauth2/revoke',
                             params={'token': credentials.token},
                             headers={'content-type': 'application/x-www-form-urlencoded'})

    status_code = getattr(response, 'status_code')
    if status_code == 200:
        return 'Credentials successfully revoked.' + print_index_table()
    else:
        return 'An error occurred.' + print_index_table()


@app.route('/clear')
def clear_credentials():
    """Delete credentials."""

    if 'credentials' in flask.session:
        del flask.session['credentials']
        return ('Credentials have been cleared.<br><br>' +
                print_index_table())


def credentials_to_dict(credentials):
    """Convert credentials to dictionary format."""

    return {'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes}

def print_index_table():
    """Testing page."""

    return ('<table>' +
            '<tr><td><a href="/test">Test an API request</a></td>' +
            '<td>Submit an API request and see a formatted JSON response. ' +
            '    Go through the authorization flow if there are no stored ' +
            '    credentials for the user.</td></tr>' +
            '<tr><td><a href="/authorize">Test the auth flow directly</a></td>' +
            '<td>Go directly to the authorization flow. If there are stored ' +
            '    credentials, you still might not be prompted to reauthorize ' +
            '    the application.</td></tr>' +
            '<tr><td><a href="/revoke">Revoke current credentials</a></td>' +
            '<td>Revoke the access token associated with the current user ' +
            '    session. After revoking credentials, if you go to the test ' +
            '    page, you should see an <code>invalid_grant</code> error.' +
            '</td></tr>' +
            '<tr><td><a href="/clear">Clear Flask session credentials</a></td>' +
            '<td>Clear the access token currently stored in the user session. ' +
            '    After clearing the token, if you <a href="/test">test the ' +
            '    API request</a> again, you should go back to the auth flow.' +
            '</td></tr></table>')


if __name__ == '__main__':
    # When running locally, disable OAuthlib's HTTPs verification.
    # ACTION ITEM for developers:
    #     When running in production *do not* leave this option enabled.
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Specify a hostname and port that are set as a valid redirect URI
    # for your API project in the Google API Console.
    app.run('localhost', 8080, debug=True)
