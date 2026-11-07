import { VAST_REFERRAL_ID } from '../../utils/vastReferral.js'

/* The sentence that makes the tagged vast.ai links honest — written once, and
   the ONE place that decides whether it shows. It renders beside each "create
   an account" moment (the API-key guide in Settings, the Setup wizard's note)
   and returns nothing when the links are untagged (empty id: forks), so no
   caller can pair tagged links with a missing disclosure, or the reverse. It
   says what the links are, what they pay, and that it costs the user nothing. */
export default function VastReferralDisclosure({ referralId = VAST_REFERRAL_ID, className }) {
  if (!String(referralId ?? '').trim()) return null
  return (
    <p className={className}>
      Our vast.ai links are referral links: open a vast.ai account through one of them and
      vast.ai pays this project 3% of what you spend there. It costs you nothing — the prices
      are identical either way, and nothing in the app behaves differently.
    </p>
  )
}
