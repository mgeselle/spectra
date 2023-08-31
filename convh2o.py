import csv
from pathlib import Path

import astropy.table as atable

# Convert HITRAN data to format palatable by spectra

infile = Path.home() / 'Downloads/64eb67df.out'
#infile = Path.home() / 'Downloads/64e10c1f.out'
with open(infile, newline='') as csvfile:
    csvreader = csv.reader(csvfile, delimiter=',')
    wli = 1
    inti = 2
    lam_vec = []
    int_vec = []
    for row in csvreader:
        if row[0] == 'nu':
            wli = 0
            inti = 1
            continue
        waven = float(row[wli])
        intens = float(row[inti])
        if intens < 1e-25:
            continue
        # HITRAN wavelengths are in vacuum
        # Convert using formula stolen from: https://www.astro.uu.se/valdwiki/Air-to-vacuum%20conversion
        lam_vac = 1.0 / waven * 1e8
        ssq = (1e4 / lam_vac)**2
        n = 1 + 0.0000834254 + 0.02406147 / (130 - ssq) + 0.00015998 / (38.9 - ssq)
        lam_air = lam_vac / n
        lam_vec.append((int(lam_air * 1000) / 1000))
        relint = int(intens * 1e27)
        int_vec.append(relint)
        print(f'{lam_air:7.3f} {relint}')
    tbl = atable.Table([lam_vec, int_vec], names=('Observed', 'Rel.'), meta={'name': 'H2O'})
    out_file = Path.home() / '.spectra_data/calib/H2O.fits'
    tbl.write(out_file)

