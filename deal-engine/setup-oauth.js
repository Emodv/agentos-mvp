/**
 * One-time script to get a Google OAuth2 refresh token.
 * Run: node setup-oauth.js
 * Paste the auth URL in your browser, approve, paste the code back.
 */
require('dotenv').config();
const { google } = require('googleapis');
const readline  = require('readline');

const SCOPES = [
  'https://www.googleapis.com/auth/gmail.compose',
  'https://www.googleapis.com/auth/gmail.readonly',
  'https://www.googleapis.com/auth/calendar.readonly',
];

async function main() {
  const client = new google.auth.OAuth2(
    process.env.GOOGLE_CLIENT_ID,
    process.env.GOOGLE_CLIENT_SECRET,
    'urn:ietf:wg:oauth:2.0:oob'
  );

  const url = client.generateAuthUrl({ access_type: 'offline', scope: SCOPES, prompt: 'consent' });

  console.log('\n=== Google OAuth2 Setup ===');
  console.log('\n1. Open this URL in your browser (make sure you are signed in as emod@banoo.marketing):\n');
  console.log(url);
  console.log('\n2. Approve all permissions.');
  console.log('3. Copy the authorization code shown.\n');

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  rl.question('Paste the authorization code here: ', async (code) => {
    rl.close();
    try {
      const { tokens } = await client.getToken(code.trim());
      console.log('\n✓ Success! Add this to your .env file:\n');
      console.log(`GOOGLE_REFRESH_TOKEN=${tokens.refresh_token}`);
      console.log('\nKeep this token safe — it gives ongoing Gmail + Calendar access.');
    } catch (err) {
      console.error('Error exchanging code:', err.message);
    }
    process.exit(0);
  });
}

main();
