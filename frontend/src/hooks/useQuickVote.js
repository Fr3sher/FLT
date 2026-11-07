import { useEffect, useRef, useState } from 'react';

/**
 * Studio quick voting: queue, touch swipe, and keyboard (left/right/Escape).
 * Do not intercept Space: global preventDefault would steal the focused
 * button native activation (accessibility). rate(imageId, rating) comes
 * from useLoraTestStudio as a stable useCallback reference.
 */
export function useQuickVote(rate) {
  const [voteQueue, setVoteQueue] = useState(null);
  const [voteIdx, setVoteIdx] = useState(0);
  // Optional mode title (e.g. reconfirm liked images) distinguishes a second
  // pass over voted images from initial voting, preventing accidental rejection
  // when users mistake previously voted images for new ones.
  const [voteTitle, setVoteTitle] = useState(null);
  const touchRef = useRef(null);

  const startVoting = (queue, title = null) => {
    if (queue.length) { setVoteQueue(queue); setVoteIdx(0); setVoteTitle(title); }
  };
  const close = () => { setVoteQueue(null); setVoteIdx(0); setVoteTitle(null); };
  const advanceVote = () => {
    if (!voteQueue || voteIdx + 1 >= voteQueue.length) close();
    else setVoteIdx((i) => i + 1);
  };
  const voteCurrent = (rating) => {
    const c = voteQueue && voteQueue[voteIdx];
    if (c) rate(c.id, rating);
    advanceVote();
  };
  const onTouchStart = (e) => {
    const t = e.touches && e.touches[0];
    if (t) touchRef.current = { x: t.clientX, y: t.clientY };
  };
  const onTouchEnd = (e) => {
    const st = touchRef.current; touchRef.current = null;
    const t = e.changedTouches && e.changedTouches[0];
    if (!st || !t) return;
    const dx = t.clientX - st.x; const dy = t.clientY - st.y;
    if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    voteCurrent(dx > 0 ? 1 : -1); // right = 👍, left = 👎
  };

  useEffect(() => {
    if (!voteQueue) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') { close(); return; }
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return; // Space deliberately ignored for accessibility
      e.preventDefault();
      voteCurrent(e.key === 'ArrowRight' ? 1 : -1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // rate stable (useCallback) → hors deps
  }, [voteQueue, voteIdx]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    voteQueue, voteIdx, voteTitle, current: voteQueue ? voteQueue[voteIdx] : null,
    startVoting, close, advanceVote, voteCurrent, onTouchStart, onTouchEnd,
  };
}
