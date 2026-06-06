export const nf = new Intl.NumberFormat('fr-FR');
export const fmt = (n: number | undefined | null) => nf.format(Math.round(n ?? 0));
export const fmtEur = (n: number | undefined | null) =>
  (n ?? 0).toLocaleString('fr-FR', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
