export const VIDEO_LANE_TOPICS = [
  { id: 'page-video-live', kind: 'page', title: 'Live channel (experimental)',
    keywords: ['live', 'live channel', 'channel', 'stream', 'streaming', 'tv channel', 'endless',
      'continuous', 'never stops', 'real time', 'real-time', 'realtime', 'vlc', 'hls', 'm3u8',
      'playlist', 'watch on another machine', 'open in vlc', 'stream address', 'scenes',
      'scene list', '{name}', 'subject', 'playback rate', 'fps', 'slow motion',
      'motion at 75 % speed', 'sustains', 'keeping up', 'behind', 'buffering', 'prefill',
      'pace', 'clips per minute', 'stop the channel', 'start the channel', 'experimental'],
    guide: { chapter: 'using-the-app', anchor: 'a-live-channel-from-your-video-lora' },
    app: { route: '/studio?lane=live' } },
  { id: 'setup-live', kind: 'page', title: 'Prepare Live',
    keywords: ['live', 'setup', 'install', 'encoder', 'ffmpeg', 'H3'],
    guide: { chapter: 'using-the-app', anchor: 'install-live' },
    app: { route: '/plugins/live/settings' } }
]
