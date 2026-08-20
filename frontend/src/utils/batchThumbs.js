/* BATCH THUMBNAILS — turn "one round trip per grid tile" into "one round trip
 * per batch" on a high-RTT link.
 *
 * The bank grid, the studio results sweep and the concept-source picker each
 * drew N <img> tags that cost a separate HTTP request (≈ the RTT) apiece. These
 * three batch endpoints — /api/bank/<id>/thumbs, /api/dataset/<id>/thumbs and
 * /api/scrape/thumbs — return MANY thumbnails in a single binary response.
 *
 * Body is a tiny index-keyed container (no base64 overhead):
 *   [u32 position][u32 length][webp bytes]  repeated, in the order requested.
 * `position` is the caller's own index into the array it sent, so a grid maps
 * each fetched blob back to the tile it belongs to. Missing/unreadable entries
 * are simply skipped, so the response may hold fewer images than requested and
 * the caller falls back to the on-demand single <img> for those.
 */

/** Decode the index-keyed binary container into `{ position: Blob }`. */
export function decodeBatchThumbs(buf) {
  const got = {};
  const dv = new DataView(buf);
  let off = 0;
  while (off + 8 <= buf.byteLength) {
    const pos = dv.getUint32(off); off += 4;
    const len = dv.getUint32(off); off += 4;
    if (off + len > buf.byteLength) break;
    got[pos] = new Blob([new Uint8Array(buf, off, len)], { type: 'image/webp' });
    off += len;
  }
  return got;
}
