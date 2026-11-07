// Format strength to two decimals while keeping 1.0 readable.
export const fmt = (s) => Number(s).toFixed(2).replace(/0$/, '').replace(/\.$/, '.0');
