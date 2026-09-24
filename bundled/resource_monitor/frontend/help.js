import { action } from '@lds/plugin-sdk/help'
export const HELP = [
  action('canvas-machine-load', '📊 Machine load, on the board and in the header (CPU · GPU · VRAM · RAM · Temp)',
    ['machine load', 'system stats', 'cpu usage', 'gpu usage', 'gpu utilisation',
     'gpu utilization', 'vram', 'vram used', 'how much vram is left', 'ram usage',
     'memory usage', 'is my gpu working', 'is anything happening', 'is it training',
     'monitor the gpu', 'hardware monitor', 'load readout', 'hide the load numbers',
     'turn off the cpu numbers', 'numbers in the canvas toolbar',
     'no gpu numbers', 'gpu percentage missing', 'why is there no vram',
     // The header mount and the temperature, in the words people ask with:
     // "a resource monitor like Crystools" is the request this answers.
     'resource monitor', 'crystools', 'monitor in the header', 'stats in the header',
     'gpu temperature', 'temperature', 'how hot is my gpu', 'degrees', 'temp',
     'no temperature', 'temperature missing', 'watch the machine from any page'],
    '/datasets', 'resource_monitor.guide', 'resource-monitor'),
  // 🧹 The button beside that readout: the same anchor, because the guide
  // explains it in the same paragraph — what holds the memory, what the
  // button gives back, and when it refuses.
  action('system-free-memory', '🧹 Free memory — unload what ComfyUI and the vision model keep in RAM',
    ['free memory', 'free ram', 'ram full', 'ram is full', 'memory full', 'out of memory',
     'clear ram', 'release memory', 'unload models', 'unload comfyui models', 'comfyui ram',
     'ram does not go down', 'memory not freed', 'vram full', 'free vram', 'clear vram',
     'unload vision model', 'unload ollama', 'unload lm studio', 'broom', 'cleanup memory'],
    '/datasets', 'resource_monitor.guide', 'resource-monitor'),
]
