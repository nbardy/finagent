from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.backends.backend_pdf import PdfPages


OUTPUT_DIR = Path("outputs")
PDF_PATH = OUTPUT_DIR / "ewy_all_charts.pdf"


def chart_title_from_name(path: Path) -> str:
    return path.stem.replace("_", " ").title()


def main() -> None:
    charts = sorted(OUTPUT_DIR.glob("*.png"))
    if not charts:
        raise RuntimeError("No PNG charts found in outputs/ to include in PDF.")

    with PdfPages(PDF_PATH) as pdf:
        for chart in charts:
            img = mpimg.imread(chart)
            fig, ax = plt.subplots(figsize=(11, 8.5))
            ax.imshow(img)
            ax.axis("off")
            ax.set_title(chart_title_from_name(chart), fontsize=14, pad=12)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    print(f"Created PDF: {PDF_PATH}")
    print(f"Charts included: {len(charts)}")


if __name__ == "__main__":
    main()
