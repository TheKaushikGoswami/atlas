import io
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps


class TradleCardRenderer:
    BG = "#15161a"
    CARD_BG = "#0f1013"
    BORDER = "#2b2f3a"
    TEXT = "#f0f3f8"
    MUTED = "#a7adba"
    GREEN = "#4caf50"
    YELLOW = "#d4b24c"
    GRAY = "#4b5260"

    @classmethod
    def color_for_proximity(cls, proximity_pct: int) -> str:
        if proximity_pct >= 90:
            return cls.GREEN
        if proximity_pct >= 70:
            return cls.YELLOW
        return cls.GRAY

    @staticmethod
    def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
        candidates = []
        if bold:
            candidates.extend(["arialbd.ttf", "DejaVuSans-Bold.ttf"])
        candidates.extend(["arial.ttf", "DejaVuSans.ttf"])
        for name in candidates:
            try:
                return ImageFont.truetype(name, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    @classmethod
    def _to_png_buffer(cls, image: Image.Image) -> io.BytesIO:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        return buf

    @staticmethod
    def _to_guess_dict(guess: Any) -> Dict[str, Any]:
        if hasattr(guess, "__dict__"):
            return dict(guess.__dict__)
        return dict(guess)

    @classmethod
    def _avatar_circle(cls, avatar_bytes: Optional[bytes], size: int) -> Image.Image:
        base = Image.new("RGBA", (size, size), "#2a2f3a")
        if avatar_bytes:
            try:
                avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB").resize((size, size))
                base = avatar.convert("RGBA")
            except Exception:
                pass

        mask = Image.new("L", (size, size), 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.ellipse((0, 0, size - 1, size - 1), fill=255)
        circ = ImageOps.fit(base, (size, size))
        circ.putalpha(mask)
        return circ

    @classmethod
    def _draw_guess_row(
        cls,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        guess: Dict[str, Any],
        label_font: ImageFont.ImageFont,
    ) -> None:
        prox = int(guess.get("proximity_pct", 0))
        color = cls.GREEN if guess.get("is_correct") else cls.color_for_proximity(prox)
        draw.rounded_rectangle((x, y, x + 24, y + 24), radius=4, fill=color, outline="#2d3340")

        line = cls.format_live_guess_line(guess)
        draw.text((x + 34, y + 4), line, fill=cls.TEXT, font=label_font)

    @classmethod
    def format_live_guess_line(cls, guess: Dict[str, Any]) -> str:
        distance = int(float(guess.get("distance_km", 0)))
        direction = guess.get("direction", "?")
        prox = int(guess.get("proximity_pct", 0))
        return f"{distance:,} km  {direction}  {prox}%"

    @classmethod
    def render_live_progress(
        cls,
        *,
        round_id: int,
        player_name: str,
        guesses: List[Any],
        status_text: str,
        avatar_bytes: Optional[bytes] = None,
    ) -> io.BytesIO:
        width, height = 980, 360
        image = Image.new("RGB", (width, height), cls.BG)
        draw = ImageDraw.Draw(image)

        title_font = cls._font(34, bold=True)
        sub_font = cls._font(22, bold=True)
        text_font = cls._font(20)

        draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=18, fill=cls.CARD_BG, outline=cls.BORDER, width=2)
        draw.text((42, 42), f"Tradle No. {round_id}", fill=cls.TEXT, font=title_font)
        draw.text((42, 84), status_text, fill=cls.MUTED, font=sub_font)

        avatar = cls._avatar_circle(avatar_bytes, 120)
        image.paste(avatar, (54, 130), avatar)
        draw.text((54, 262), player_name[:18], fill=cls.TEXT, font=text_font)

        grid_x, grid_y = 220, 136
        row_h = 30
        normalized = [cls._to_guess_dict(g) for g in guesses][:6]
        for i, g in enumerate(normalized):
            cls._draw_guess_row(draw, grid_x, grid_y + (i * row_h), g, text_font)

        # Empty slots for remaining guesses
        for i in range(len(normalized), 6):
            y = grid_y + (i * row_h)
            draw.rounded_rectangle((grid_x, y, grid_x + 24, y + 24), radius=4, outline="#323845", width=2, fill="#181d25")
            draw.text((grid_x + 34, y + 4), "- - -", fill="#667086", font=text_font)

        return cls._to_png_buffer(image)

    @classmethod
    def _draw_player_panel(
        cls,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        *,
        name: str,
        score: Optional[int],
        guesses: List[Any],
        avatar_bytes: Optional[bytes],
    ) -> None:
        draw.rounded_rectangle((x, y, x + width, y + 240), radius=14, fill="#111318", outline=cls.BORDER, width=2)

        avatar = cls._avatar_circle(avatar_bytes, 74)
        image.paste(avatar, (x + 18, y + 16), avatar)

        name_font = cls._font(20, bold=True)
        small_font = cls._font(18)
        draw.text((x + 102, y + 28), name[:14], fill=cls.TEXT, font=name_font)
        score_label = f"{score}/6" if score is not None else "-"
        draw.text((x + 102, y + 58), f"Score: {score_label}", fill=cls.MUTED, font=small_font)

        g = [cls._to_guess_dict(i) for i in guesses][:6]
        gx, gy = x + 18, y + 104
        for idx in range(6):
            col = idx % 6
            if idx < len(g):
                prox = int(g[idx].get("proximity_pct", 0))
                fill = cls.GREEN if g[idx].get("is_correct") else cls.color_for_proximity(prox)
            else:
                fill = "#191d24"
            draw.rectangle((gx + col * 28, gy, gx + col * 28 + 22, gy + 22), fill=fill, outline="#2f3542")

    @classmethod
    def render_round_announcement(
        cls,
        *,
        new_round_id: int,
        previous_round_id: Optional[int],
        players: List[Dict[str, Any]],
    ) -> io.BytesIO:
        width, height = 1280, 720
        image = Image.new("RGB", (width, height), cls.BG)
        draw = ImageDraw.Draw(image)

        h1 = cls._font(44, bold=True)
        h2 = cls._font(28, bold=True)
        text = cls._font(22)

        draw.text((42, 34), f"New Tradle Round #{new_round_id}", fill=cls.TEXT, font=h1)
        if previous_round_id is not None:
            draw.text((42, 96), f"Yesterday's results (Round #{previous_round_id})", fill=cls.MUTED, font=h2)
        else:
            draw.text((42, 96), "No previous round yet.", fill=cls.MUTED, font=h2)

        if not players:
            draw.rounded_rectangle((42, 150, width - 42, 320), radius=14, fill=cls.CARD_BG, outline=cls.BORDER, width=2)
            draw.text((72, 218), "No one finished the previous Tradle round.", fill=cls.TEXT, font=text)
            return cls._to_png_buffer(image)

        top = players[:6]
        panel_w = 192
        gap = 12
        start_x = 42
        y = 160

        for idx, p in enumerate(top):
            px = start_x + idx * (panel_w + gap)
            cls._draw_player_panel(
                image,
                draw,
                px,
                y,
                panel_w,
                name=p.get("name", "Player"),
                score=p.get("score"),
                guesses=p.get("guesses", []),
                avatar_bytes=p.get("avatar_bytes"),
            )

        ranking_y = 430
        draw.rounded_rectangle((42, ranking_y, width - 42, height - 42), radius=14, fill=cls.CARD_BG, outline=cls.BORDER, width=2)
        draw.text((64, ranking_y + 22), "Leaderboard", fill=cls.TEXT, font=h2)
        line_font = cls._font(24)
        for i, p in enumerate(top):
            score = "-" if p.get("score") is None else f"{p['score']}/6"
            rank = "👑 " if i == 0 else ""
            line = f"{rank}{score}: {p.get('name', 'Player')}"
            draw.text((64, ranking_y + 70 + i * 36), line, fill=cls.MUTED if i else cls.TEXT, font=line_font)

        return cls._to_png_buffer(image)
