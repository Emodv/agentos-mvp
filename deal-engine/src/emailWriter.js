const Anthropic = require('@anthropic-ai/sdk');

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const MODEL  = process.env.ANTHROPIC_MODEL || 'claude-sonnet-4-5-20251001';

const SENDER_SIG = `Emod Vafa
Banoo Marketing — PPC & Lead Gen for Law Firms
${process.env.CALCOM_URL || 'https://cal.com/emodvafa'}`;

/**
 * PATH A: warm re-engagement for a prospect with prior email history.
 */
async function writeWarmEmail(prospect) {
  const { name, email, lastDate, subject, snippet } = prospect;
  const firstName = name.split(' ')[0];
  const dateLabel = lastDate
    ? new Date(lastDate).toLocaleDateString('en-CA', { month: 'long', year: 'numeric' })
    : 'a few months ago';

  const prompt = `Write a short, personalized re-engagement email from Emod Vafa at Banoo Marketing
to ${name} (${email}), a personal injury lawyer in Ontario.

Context:
- Last email exchange: ${dateLabel}
- Previous subject: "${subject}"
- Snippet: "${snippet}"
- Banoo Marketing specialises in Google Ads and lead generation for PI law firms in Toronto/Ontario

Requirements:
- Subject line: personalized, references something specific, NOT generic
- Body: 3-4 short lines ONLY
- Mention the previous conversation naturally
- CTA: suggest a quick reconnect call for July — include this Calendly link: ${process.env.CALCOM_URL || 'https://cal.com/emodvafa'}
- Sign off as Emod Vafa, Banoo Marketing
- Tone: warm, professional, direct — not salesy

Return JSON only:
{"subject": "...", "body": "..."}`;

  const msg = await client.messages.create({
    model: MODEL,
    max_tokens: 512,
    messages: [{ role: 'user', content: prompt }],
  });

  const text = msg.content[0].text.trim();
  const parsed = JSON.parse(text.match(/\{[\s\S]*\}/)[0]);
  return {
    to:      email,
    subject: parsed.subject,
    body:    parsed.body + `\n\n${SENDER_SIG}`,
    path:    'A_warm',
  };
}

/**
 * PATH B: cold authority email for a new prospect with no prior history.
 */
async function writeColdEmail(prospect) {
  const { name, email, title, company, city, notes } = prospect;
  const firstName = name.split(' ')[0] || 'there';
  const firmContext = company ? `at ${company}` : '';
  const cityCtx    = city    ? `in ${city}`     : 'in Ontario';

  const prompt = `Write a short, personalized cold outreach email from Emod Vafa at Banoo Marketing
to ${name} ${firmContext}, a personal injury lawyer ${cityCtx}.

Context about this prospect: ${notes || 'Ontario-based PI lawyer, solo to 20-person firm'}

Banoo Marketing's value prop:
- Google Ads management specifically for PI law firms
- Focus: Toronto, Mississauga, Brampton, Hamilton, Ottawa
- Outcome: more qualified intake leads, lower cost per signed case

Requirements:
- Subject line: specific to them, NOT generic ("Quick question" / "Partnership" are banned)
- Body: 3-4 short lines MAX
- Reference something specific about their firm or location
- CTA: one ask only — 15-minute call. Include: ${process.env.CALCOM_URL || 'https://cal.com/emodvafa'}
- Tone: confident, peer-to-peer, not salesy
- Sign as Emod Vafa, Banoo Marketing

Return JSON only:
{"subject": "...", "body": "..."}`;

  const msg = await client.messages.create({
    model: MODEL,
    max_tokens: 512,
    messages: [{ role: 'user', content: prompt }],
  });

  const text = msg.content[0].text.trim();
  const parsed = JSON.parse(text.match(/\{[\s\S]*\}/)[0]);
  return {
    to:      email,
    subject: parsed.subject,
    body:    parsed.body + `\n\n${SENDER_SIG}`,
    path:    'B_cold',
  };
}

/**
 * Route to the right path based on whether there's prior history.
 */
async function writeEmail(prospect) {
  if (prospect.source === 'gmail' && prospect.snippet) {
    return writeWarmEmail(prospect);
  }
  return writeColdEmail(prospect);
}

module.exports = { writeEmail };
