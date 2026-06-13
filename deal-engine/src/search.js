const Anthropic = require('@anthropic-ai/sdk');

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

const MODEL = process.env.ANTHROPIC_MODEL || 'claude-sonnet-4-5-20251001';

/**
 * Use Claude to identify 2-3 PI law firms in Ontario that are actively
 * hiring or growing (based on its training knowledge).
 * Returns array of { name, email, company, city, notes }
 */
async function findGrowingPIFirms(logger, limit = 3) {
  try {
    const prompt = `You are a sales research assistant for Banoo Marketing, a digital marketing agency
that specialises in Google Ads and lead generation for personal injury law firms in Ontario, Canada.

Task: Identify ${limit} personal injury law firms in Ontario (Toronto, Mississauga, Brampton,
Hamilton, or Ottawa) that appear to be actively growing — e.g., recently expanded, opened new offices,
hiring lawyers, or investing in marketing.

For each firm, provide:
1. Firm name
2. City
3. A specific reason they seem to be growing or need lead gen help
4. A realistic contact email format (e.g., info@firmname.ca or firstname@firmname.ca)
5. A key partner/lawyer name if known

Format as JSON array:
[
  {
    "company": "...",
    "city": "...",
    "email": "...",
    "name": "...",
    "notes": "specific growth signal or pain point"
  }
]

Focus on solo to 20-lawyer firms. Return ONLY the JSON array, no other text.`;

    const msg = await client.messages.create({
      model: MODEL,
      max_tokens: 1024,
      messages: [{ role: 'user', content: prompt }],
    });

    const text = msg.content[0].text.trim();
    const jsonMatch = text.match(/\[[\s\S]*\]/);
    if (!jsonMatch) { logger.warn('Claude search: no JSON in response'); return []; }

    const firms = JSON.parse(jsonMatch[0]);
    logger.info(`Claude web research: identified ${firms.length} growing PI firms`);

    return firms.slice(0, limit).map(f => ({ ...f, source: 'claude_research' }));
  } catch (err) {
    logger.warn(`Claude research failed: ${err.message}`);
    return [];
  }
}

module.exports = { findGrowingPIFirms };
