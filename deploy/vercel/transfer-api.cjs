const crypto = require('node:crypto');

module.exports = async (req, res) => {
  const expected = process.env.RA2_TRANSFER_KEY || '';
  const supplied = req.headers['x-transfer-key'] || '';
  if (!expected || typeof supplied !== 'string' || supplied.length !== expected.length ||
      !crypto.timingSafeEqual(Buffer.from(supplied), Buffer.from(expected))) {
    res.status(404).end(); return;
  }
  if (req.method !== 'POST') { res.status(405).end(); return; }
  const pathname = req.body?.pathname;
  if (typeof pathname !== 'string' || !/^(program|resources)\/[a-f0-9]{64}\.bin(\.deflate)?$/.test(pathname)) {
    res.status(400).json({error: 'Invalid transfer object'}); return;
  }
  try {
    const source = await fetch(process.env.RA2_TRANSFER_ORIGIN + pathname, {signal: AbortSignal.timeout(120000)});
    if (!source.ok) throw new Error('Source unavailable: ' + source.status);
    const bytes = Buffer.from(await source.arrayBuffer());
    if (bytes.length > 1048576) throw new Error('Transfer object too large');
    const target = 'https://vercel.com/api/blob/?' + new URLSearchParams({pathname});
    const response = await fetch(target, {
      method: 'PUT', body: bytes, signal: AbortSignal.timeout(120000),
      headers: {
        authorization: 'Bearer ' + process.env.BLOB_READ_WRITE_TOKEN,
        'x-api-version': '12', 'x-vercel-blob-access': 'public',
        'x-add-random-suffix': '0', 'x-allow-overwrite': '1',
        'x-content-type': 'application/octet-stream',
        'x-content-length': String(bytes.length), 'x-cache-control-max-age': '31536000'
      }
    });
    const result = await response.json();
    if (!response.ok) throw new Error('Storage upload failed: ' + response.status);
    res.setHeader('Cache-Control', 'no-store');
    res.status(200).json({pathname, url: result.url, size: bytes.length});
  } catch (error) {
    res.status(502).json({error: error.message});
  }
};
