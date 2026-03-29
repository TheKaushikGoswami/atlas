import matplotlib.pyplot as plt
import squarify
import io
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class TradleTreemap:
    # OEC / HS Category Colors (rough approximations)
    CATEGORY_COLORS = {
        "Animal Products": "#82b2d2",
        "Vegetable Products": "#8cc63f",
        "Animal and Vegetable Bi-Products": "#c3d69b",
        "Foodstuffs": "#f68b1f",
        "Mineral Products": "#336633",
        "Chemical Products": "#ffff00",
        "Plastics and Rubbers": "#99cc00",
        "Raw Hides, Skins, Leathers, and Furs": "#996633",
        "Wood and Wood Products": "#663300",
        "Paper Goods": "#996600",
        "Textiles": "#003366",
        "Footwear and Headwear": "#3399ff",
        "Stone and Glass": "#999999",
        "Precious Metals": "#cc9900",
        "Metals": "#ff66cc",
        "Machinery": "#3399ff",
        "Transportation": "#6600cc",
        "Instruments": "#cc0066",
        "Weapons": "#000000",
        "Miscellaneous": "#999999",
        "Arts and Antiques": "#660033"
    }

    @classmethod
    def generate(cls, exports: List[Dict[str, Any]], total_val_str: str) -> io.BytesIO:
        """
        Generate a treemap PNG from export data.
        exports: list of {"product": str, "value": float, "share": float}
        """
        # Sort exports by value descending
        exports = sorted(exports, key=lambda x: x["value"], reverse=True)
        
        values = [e["value"] for e in exports]
        labels = [f"{e['product']}\n{e['share']*100:.1f}%" for e in exports]
        
        # In a real OEC-like treemap, we'd have category info. 
        # For now, we'll use a varied color palette or try to infer category.
        # Since our fetch script didn't keep category, we'll rotate colors for now.
        # colors = [plt.cm.Spectral(i/float(len(values))) for i in range(len(values))]
        # Actually, let's use a nice custom palette.
        palette = [
            "#5cb85c", "#5bc0de", "#f0ad4e", "#d9534f", "#337ab7",
            "#8cc63f", "#f68b1f", "#336633", "#ff66cc", "#6600cc"
        ]
        colors = [palette[i % len(palette)] for i in range(len(values))]

        # Create plot
        fig, ax = plt.subplots(figsize=(10, 8), dpi=100)
        fig.patch.set_facecolor('#1e1e1e') # Dark mode background
        
        squarify.plot(
            sizes=values, 
            label=labels[:10], # Only label top 10 for clarity
            color=colors, 
            alpha=.8,
            ax=ax,
            text_kwargs={'fontsize': 10, 'color': 'white', 'fontweight': 'bold'}
        )
        
        plt.title(f"Top exports (Total: {total_val_str})", color='white', pad=20, size=16)
        plt.axis('off')
        
        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)
        return buf
