"""The narrated Faida film, drawn in Manim.

Every scene reads build/timings.json (written by narration.py) and starts each
beat of its animation when the sentence it illustrates starts, so the pictures
follow the voice. Scene lengths are whole bars of the music, and a gold and
Date Palm wipe crosses every cut.

    manim -qh film.py Film       # 1080p60 -> media/videos/film/1080p60/Film.mp4
    manim -ql film.py Film       # 480p15 draft
"""

import json
from pathlib import Path

from manim import (
    BOLD, DOWN, LEFT, MEDIUM, ORIGIN, RIGHT, SEMIBOLD, ULTRABOLD, UP,
    AnimationGroup, AnnularSector, Annulus, ArcBetweenPoints, Circle, Create, CubicBezier,
    Dot, FadeIn, FadeOut, GrowFromEdge, Indicate, LaggedStart, Line, MoveAlongPath,
    Polygon, Rectangle, RoundedRectangle, Scene, SVGMobject, Text, Transform, ValueTracker,
    VGroup, Write, always_redraw, config, linear, rate_functions, smooth,
)

HERE = Path(__file__).parent
TIMINGS = json.loads((HERE / "build" / "timings.json").read_text())
MARK_SVG = str(HERE.parent.parent.parent / "apps" / "web" / "public" / "brand" / "faida-mark.svg")

# brand tokens (apps/web/src/app/globals.css)
CREAM, PAPER, INK = "#fbf6ec", "#ffffff", "#172421"
PALM, PALM_DEEP, GOLD, GOLD_SOFT = "#153e35", "#0e2b25", "#e3a13b", "#f8eed9"
SAGE, MIST, STONE, VERIFIED, CAUTION = "#9cc8b3", "#e7efea", "#52625d", "#1d6d50", "#80520a"
LINE_GREY = "#e3e7e4"

config.background_color = CREAM
out = rate_functions.ease_out_cubic
back = rate_functions.ease_out_back


# ---------- building blocks ----------
# Text is drawn at four times its size and scaled down: at small sizes Pango's
# layout loses the spaces between words ("Karakchai").
SUPERSAMPLE = 4


def txt(s, size=32, color=INK, weight=MEDIUM, font="Inter", **kw):
    return Text(s, font=font, font_size=size * SUPERSAMPLE, color=color, weight=weight, **kw).scale(1 / SUPERSAMPLE)


def head(s, size=72, color=INK, **kw):
    return txt(s, size, color, ULTRABOLD, "Manrope", **kw)


def mono(s, size=16, color=INK):
    return txt(s, size, color, MEDIUM, "DejaVu Sans Mono")


def card(w, h, color=PAPER, r=0.14, opacity=1.0, stroke=None):
    rect = RoundedRectangle(corner_radius=r, width=w, height=h, fill_color=color, fill_opacity=opacity, stroke_width=0)
    if stroke:
        rect.set_stroke(stroke, 2)
    return rect


def shadowed(mob, dx=0.06, dy=-0.1, opacity=0.18):
    sh = mob.copy().set_fill(INK, opacity).set_stroke(width=0).shift([dx, dy, 0])
    return VGroup(sh, mob)


def mark(reversed_=False):
    m = SVGMobject(MARK_SVG, height=1)
    if reversed_:
        m[0].set_fill(SAGE, 1)
        m[2].set_fill(CREAM, 1)
    return m


def check_icon(color=VERIFIED, r=0.2):
    c = Circle(radius=r, fill_color=color, fill_opacity=1, stroke_width=0)
    tick = VGroup(Line([-0.42 * r, 0, 0], [-0.1 * r, -0.32 * r, 0]), Line([-0.1 * r, -0.32 * r, 0], [0.45 * r, 0.3 * r, 0]))
    tick.set_stroke(PAPER, 5 * r / 0.2)
    return VGroup(c, tick)


def up_icon(color=GOLD, r=0.2):
    c = Circle(radius=r, fill_color=color, fill_opacity=1, stroke_width=0)
    arrow = VGroup(Line([-0.45 * r, -0.3 * r, 0], [-0.1 * r, 0.05 * r, 0]), Line([-0.1 * r, 0.05 * r, 0], [0.1 * r, -0.15 * r, 0]),
                   Line([0.1 * r, -0.15 * r, 0], [0.45 * r, 0.25 * r, 0]))
    arrow.set_stroke(PAPER, 4 * r / 0.2)
    return VGroup(c, arrow)


def invoice(name, total, w=2.3, h=3.0, seed=0):
    paper = card(w, h, PAPER, 0.06)
    title = txt(name, 15, INK, BOLD, "Manrope")
    meta = txt(f"Tax invoice #{10470 + seed * 7}", 10, STONE)
    widths = [0.9, 0.72, 0.84, 0.64, 0.8, 0.58, 0.76][seed % 3:] + [0.7, 0.82]
    lines = VGroup(*[card(w * 0.8 * f, 0.06, LINE_GREY, 0.03) for f in widths[:7]]).arrange(DOWN, buff=0.13, aligned_edge=LEFT)
    rule = Line([0, 0, 0], [w * 0.84, 0, 0], color=INK, stroke_width=2)
    tot = VGroup(txt("Total", 12, INK, BOLD), txt(f"AED {total}", 12, INK, BOLD))
    body = VGroup(title, meta, lines).arrange(DOWN, buff=0.1, aligned_edge=LEFT)
    body[2].shift(DOWN * 0.1)
    body.move_to(paper).align_to(paper, UP).shift(DOWN * 0.22)
    body.align_to(paper, LEFT).shift(RIGHT * 0.2)
    rule.next_to(paper.get_bottom(), UP, buff=0.42)
    tot[0].next_to(rule, DOWN, buff=0.08).align_to(rule, LEFT)
    tot[1].next_to(rule, DOWN, buff=0.08).align_to(rule, RIGHT)
    return shadowed(VGroup(paper, body, rule, tot), 0.05, -0.08, 0.25)


def phone(w=3.3, h=6.9, title="Faida", subtitle="Al Quoz branch"):
    body = RoundedRectangle(corner_radius=0.48, width=w, height=h, fill_color="#0b1f1b", fill_opacity=1, stroke_color="#2a4a43", stroke_width=2)
    screen = RoundedRectangle(corner_radius=0.38, width=w - 0.2, height=h - 0.2, fill_color="#f1ede4", fill_opacity=1, stroke_width=0)
    bar = RoundedRectangle(corner_radius=0.38, width=w - 0.2, height=1.2, fill_color=PALM, fill_opacity=1, stroke_width=0)
    bar.align_to(screen, UP)
    patch = Rectangle(width=w - 0.2, height=0.45, fill_color=PALM, fill_opacity=1, stroke_width=0).align_to(bar, DOWN)
    notch = RoundedRectangle(corner_radius=0.12, width=0.95, height=0.24, fill_color="#0b1f1b", fill_opacity=1, stroke_width=0)
    notch.move_to(screen.get_top() + DOWN * 0.2)
    avatar = Circle(radius=0.22, fill_color=CREAM, fill_opacity=1, stroke_width=0)
    logo = mark().scale_to_fit_width(0.26).move_to(avatar)
    names = VGroup(txt(title, 17, CREAM, BOLD, "Manrope"), txt(subtitle, 11, SAGE)).arrange(DOWN, aligned_edge=LEFT, buff=0.04)
    who = VGroup(VGroup(avatar, logo), names).arrange(RIGHT, buff=0.16).move_to(bar).align_to(bar, LEFT).shift(RIGHT * 0.25 + DOWN * 0.18)
    g = VGroup(shadowed(body, 0.1, -0.16, 0.2), screen, bar, patch, notch, who)
    g.screen = screen
    return g


def bubble(content, outgoing=False, pad=0.14, color=None):
    color = color or ("#d7eadf" if outgoing else PAPER)
    box = card(content.width + 2 * pad, content.height + 2 * pad, color, 0.14)
    content.move_to(box)
    return VGroup(box, content)


def row(left, right, width, size=12, color=INK):
    a, b = txt(left, size, color), txt(right, size, STONE)
    b.next_to(a, RIGHT, buff=0).shift(RIGHT * (width - a.width - b.width))
    return VGroup(a, b)


def whole_frames(seconds):
    """Round a duration to whole frames. Manim's clock adds the nominal run time
    while the file gets whole frames, so over a hundred animations the picture
    would drift from the voice; on whole frames the two cannot disagree."""
    frames = max(1, round(seconds * config.frame_rate))
    return frames / config.frame_rate - 1e-6


class Film(Scene):
    # ---------- timing ----------
    def play(self, *args, **kwargs):
        anims = self.compile_animations(*args, **{k: v for k, v in kwargs.items() if k != "run_time"})
        run_time = kwargs.pop("run_time", None) or self.get_run_time(anims)
        return super().play(*anims, run_time=whole_frames(run_time), **{k: v for k, v in kwargs.items() if k != "run_time"})

    def wait(self, duration=1.0, *args, **kwargs):
        return super().wait(whole_frames(duration), *args, **kwargs)

    def until(self, t_local):
        """Wait until t_local seconds into the current scene; say so if we are late."""
        target = self.t0 + t_local
        gap = target - self.time
        if gap > 1 / config.frame_rate:
            self.wait(gap)
        elif gap < -0.1:
            print(f"  [{self.scene_id}] {-gap:.2f}s behind at {t_local:.2f}s")

    def said(self, i, frac=0.0):
        s = self.sentences[i]
        return s["start"] + frac * (s["end"] - s["start"])

    # ---------- the wipe across every cut ----------
    def make_wipes(self):
        def panel(color):
            p = Polygon([-9, -4.6, 0], [11, -4.6, 0], [9, 4.6, 0], [-11, 4.6, 0], fill_color=color, fill_opacity=1, stroke_width=0)
            return p.shift(RIGHT * 22)
        self.wipe_a, self.wipe_b = panel(GOLD), panel(PALM)

    def wipe_in(self, dur=0.32):
        self.add(self.wipe_a, self.wipe_b)
        self.wipe_a.move_to(RIGHT * 22)
        self.wipe_b.move_to(RIGHT * 25)
        self.play(self.wipe_a.animate.move_to(LEFT * 3), self.wipe_b.animate.move_to(ORIGIN), run_time=dur, rate_func=rate_functions.ease_in_cubic)

    def wipe_out(self, bg, dur=0.34):
        keep = {self.wipe_a, self.wipe_b}
        self.remove(*[m for m in self.mobjects if m not in keep])
        self.camera.background_color = bg
        self.play(self.wipe_a.animate.move_to(LEFT * 25), self.wipe_b.animate.move_to(LEFT * 22), run_time=dur, rate_func=out)
        self.remove(self.wipe_a, self.wipe_b)

    # ---------- the film ----------
    def construct(self):
        self.make_wipes()
        backgrounds = {"hook": CREAM, "problem": PALM_DEEP, "brand": CREAM, "forward": CREAM, "plate": CREAM,
                       "dashboard": MIST, "brief": PALM, "close": PALM_DEEP}
        scenes = TIMINGS["scenes"]
        for n, sc in enumerate(scenes):
            self.scene_id, self.sentences = sc["id"], sc["sentences"]
            self.t0 = sc["start"]
            if n:
                self.wipe_out(backgrounds[sc["id"]])
            else:
                self.camera.background_color = backgrounds[sc["id"]]
            getattr(self, sc["id"])()
            last = n == len(scenes) - 1
            self.until(sc["duration"] - (0 if last else 0.32))
            if not last:
                self.wipe_in()

    # 1 · the hook
    def hook(self):
        eyebrow = txt("A DAY AT THE COUNTER", 20, STONE, SEMIBOLD).to_corner(UP + LEFT, buff=1.0).shift(DOWN * 0.6)
        sold = ValueTracker(0)
        number = always_redraw(lambda: head(f"AED {int(sold.get_value()):,}", 120, PALM).next_to(eyebrow, DOWN, buff=0.35, aligned_edge=LEFT))
        word = head("sold.", 120, INK)
        self.until(0.25)
        self.play(FadeIn(eyebrow, shift=UP * 0.2), FadeIn(number, shift=UP * 0.3), run_time=0.5, rate_func=out)
        self.play(sold.animate.set_value(6420), run_time=1.6, rate_func=out)
        word.next_to(number, RIGHT, buff=0.35).align_to(number, DOWN)
        self.play(FadeIn(word, shift=LEFT * 0.3), run_time=0.4, rate_func=out)

        # the day's takings as one bar
        W = 12.0
        bar = card(W, 0.7, PALM, 0.12).move_to([0, -1.9, 0])
        bar_label = txt("AED 6,420 sold", 22, CREAM, SEMIBOLD).move_to(bar).align_to(bar, LEFT).shift(RIGHT * 0.3)
        self.play(GrowFromEdge(bar, LEFT), run_time=0.8, rate_func=out)
        self.play(FadeIn(bar_label), run_time=0.3)

        # "how much did you keep?" - the bar splits into what went out and a question
        self.until(self.said(1))
        q = head("How much did you keep?", 72, INK, t2c={"keep?": GOLD}).next_to(number, DOWN, buff=0.5, aligned_edge=LEFT)
        costs = card(W * 0.64, 0.7, STONE, 0.12).align_to(bar, LEFT).align_to(bar, DOWN)
        kept = card(W * 0.33, 0.7, GOLD, 0.12).align_to(bar, RIGHT).align_to(bar, DOWN)
        costs_l = txt("ingredients, suppliers ...", 22, CREAM, SEMIBOLD).move_to(costs)
        kept_l = head("kept ?", 30, INK).move_to(kept)
        self.play(FadeIn(q, shift=UP * 0.25), run_time=0.6, rate_func=out)
        self.play(Transform(bar, VGroup(costs, kept)), FadeOut(bar_label), run_time=0.7, rate_func=smooth)
        self.play(FadeIn(costs_l), FadeIn(kept_l, scale=1.4), run_time=0.4, rate_func=out)
        self.play(Indicate(kept_l, color=INK, scale_factor=1.25), run_time=0.8)

    # 2 · the problem
    def problem(self):
        lines = [head(s, 56, CREAM, t2c={"quietly.": GOLD}) for s in ["Invoices pile up.", "Prices creep up, quietly.", "Your margin shrinks."]]
        VGroup(*lines).arrange(DOWN, aligned_edge=LEFT, buff=0.35).to_edge(LEFT, buff=0.8).shift(UP * 0.3)

        names = [("Al Madina Foodstuff", "716.89"), ("Gulf Dairy Trading", "1,284.50"), ("Emirates Poultry", "2,410.00"),
                 ("Fresh Bake Supplies", "388.20"), ("Al Ain Farms", "942.75"), ("Deira Spice House", "215.40")]
        pile = VGroup()
        for i, (n, t) in enumerate(names):
            inv = invoice(n, t, seed=i).rotate(((i * 47) % 26 - 13) * 0.0174)
            inv.move_to([4.3 + (i % 3) * 0.55 - 0.5, 0.9 - (i % 2) * 0.5 + (i * 0.13 % 0.4), 0])
            pile.add(inv)

        self.until(self.said(0))
        self.play(FadeIn(lines[0], shift=UP * 0.3), run_time=0.5, rate_func=out)
        self.play(LaggedStart(*[FadeIn(p, shift=UP * 3 + LEFT * 0.8, scale=0.9) for p in pile], lag_ratio=0.18), run_time=1.0, rate_func=out)

        # prices creep up: a price line climbing out of the pile
        self.until(self.said(1))
        self.play(FadeIn(lines[1], shift=UP * 0.3), pile.animate.scale(0.45).move_to([4.6, 2.5, 0]).set_opacity(0.3), run_time=0.6, rate_func=out)
        pts = [[2.4, -0.2], [3.1, -0.15], [3.7, 0.1], [4.4, 0.15], [5.0, 0.55], [5.7, 0.65], [6.3, 1.1]]
        pts = [[x, y - 0.6, 0] for x, y in pts]
        base = Line([2.3, -1.0, 0], [6.5, -1.0, 0], color=SAGE, stroke_width=2, stroke_opacity=0.4)
        price = VGroup(*[Line(pts[i], pts[i + 1], color=GOLD, stroke_width=7) for i in range(len(pts) - 1)])
        dots = VGroup(*[Dot(p, radius=0.08, color=GOLD) for p in pts[1::2]])
        tag = VGroup(up_icon(r=0.2), txt("Milk powder +AED 4.00", 22, CREAM, BOLD)).arrange(RIGHT, buff=0.14)
        tag.next_to(pts[-1], UP, buff=0.25).align_to(base, RIGHT)
        self.play(Create(base), run_time=0.3)
        self.play(Create(price), LaggedStart(*[FadeIn(d, scale=2) for d in dots], lag_ratio=0.4), run_time=1.2, rate_func=linear)
        self.play(FadeIn(tag, shift=UP * 0.2, scale=0.8), run_time=0.4, rate_func=back)

        # the margin bar shrinks as the price line rises
        self.until(self.said(2))
        self.play(FadeIn(lines[2], shift=UP * 0.3), run_time=0.5, rate_func=out)
        full = card(4.2, 0.5, SAGE, 0.1).move_to([4.4, -2.3, 0])
        margin = card(4.2 * 0.67, 0.5, SAGE, 0.1).align_to(full, LEFT).align_to(full, DOWN)
        track = card(4.2, 0.5, "#1c4a40", 0.1).move_to(full)
        pct = ValueTracker(67)
        label = always_redraw(lambda: txt(f"margin {int(pct.get_value())}%", 22, CREAM, SEMIBOLD).next_to(track, UP, buff=0.14, aligned_edge=LEFT))
        self.play(FadeIn(track), GrowFromEdge(margin, LEFT), FadeIn(label), run_time=0.5, rate_func=out)
        self.play(margin.animate.stretch_to_fit_width(4.2 * 0.52, about_edge=LEFT), pct.animate.set_value(52), run_time=1.4, rate_func=smooth)

    # 3 · the brand
    def brand(self):
        m = mark().scale_to_fit_height(2.3)
        word = txt("faida", 190, INK, SEMIBOLD, "Manrope")
        lockup = VGroup(m, word).arrange(RIGHT, buff=0.55).shift(UP * 0.5)
        word.align_to(m, DOWN).shift(DOWN * 0.12)
        line = txt("Profit, in plain sight.", 52, PALM, BOLD, "Manrope", t2c={"plain sight.": GOLD})
        line.next_to(lockup, DOWN, buff=0.8)
        self.until(self.said(0) - 0.25)
        self.play(LaggedStart(*[FadeIn(t, shift=DOWN * 0.9, scale=0.4) for t in m], lag_ratio=0.28), run_time=0.9, rate_func=back)
        self.play(Write(word), run_time=0.7)
        self.until(self.said(1))
        self.play(FadeIn(line, shift=UP * 0.3), run_time=0.6, rate_func=out)

    # 4 · forward the invoice
    def forward(self):
        ph = phone().move_to([-4.4, -0.05, 0])
        step = VGroup(head("01", 30, GOLD), Line(ORIGIN, RIGHT * 0.8, color=GOLD, stroke_width=4)).arrange(RIGHT, buff=0.2)
        title = head("Forward the invoice.", 58, INK)
        sub = txt("One WhatsApp number. No app, no login, no typing.", 24, STONE)
        right = VGroup(step, title, sub).arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        right.move_to([0, 1.9, 0]).align_to([-1.9, 0, 0], LEFT)
        step.align_to(title, LEFT)

        self.play(FadeIn(ph, shift=UP * 2.5), run_time=0.7, rate_func=out)
        self.until(self.said(0))
        self.play(FadeIn(step, shift=RIGHT * 0.3), FadeIn(title, shift=UP * 0.3), run_time=0.5, rate_func=out)
        self.play(FadeIn(sub, shift=UP * 0.2), run_time=0.4, rate_func=out)

        # the photo arcs from the paper into the chat as an outgoing bubble
        paper = invoice("Al Madina Foodstuff", "716.89", seed=0).scale(0.8).move_to([-7.8, -1.6, 0]).rotate(0.2)
        thumb = invoice("Al Madina Foodstuff", "716.89", seed=0).scale(0.55)
        sent = bubble(VGroup(txt("Forwarded", 10, STONE), thumb, txt("09:42", 9, STONE)).arrange(DOWN, buff=0.06, aligned_edge=RIGHT), outgoing=True, pad=0.08)
        sent.move_to(ph.screen).align_to(ph.screen, RIGHT).shift(LEFT * 0.14 + UP * 1.05)
        self.add(paper)
        path = ArcBetweenPoints(paper.get_center(), sent.get_center(), angle=-1.2)
        self.play(MoveAlongPath(paper, path), paper.animate.rotate(-0.2), run_time=0.9, rate_func=smooth)
        self.play(Transform(paper, sent), run_time=0.35)

        # Faida's reply, in the product's own words
        self.until(self.said(1))
        w = 2.55
        reply_lines = VGroup(
            VGroup(check_icon(r=0.1), txt("Read it", 13, INK, BOLD)).arrange(RIGHT, buff=0.08),
            txt("Al Madina Foodstuff · #10482", 11, INK),
            head("AED 716.89", 26, INK),
            row("Milk powder", "4 × 47.00", w), row("Evaporated milk", "24 × 3.25", w),
            row("Tea dust", "6 × 28.50", w), row("Sugar", "2 × 62.00", w), row("+ 8 more lines", "", w, color=STONE),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.07)
        chip = bubble(VGroup(up_icon(CAUTION, 0.09), txt("Milk powder is up AED 4.00", 11, CAUTION, BOLD)).arrange(RIGHT, buff=0.08), color=GOLD_SOFT, pad=0.07)
        ok = txt("Reply OK to confirm.", 11, INK, t2w={"OK": BOLD})
        reply = bubble(VGroup(reply_lines, chip, ok).arrange(DOWN, aligned_edge=LEFT, buff=0.1), pad=0.14)
        reply.align_to(ph.screen, LEFT).shift(RIGHT * 0.12)
        reply.next_to(paper, DOWN, buff=0.12).align_to(ph.screen, LEFT).shift(RIGHT * 0.12)
        chip.set_opacity(0)
        ok.set_opacity(0)
        checks = VGroup(
            VGroup(check_icon(r=0.22), txt("Every line read", 30, PALM, SEMIBOLD)).arrange(RIGHT, buff=0.25),
            VGroup(check_icon(r=0.22), txt("Adds up to AED 716.89", 30, PALM, SEMIBOLD)).arrange(RIGHT, buff=0.25),
            VGroup(up_icon(r=0.22), txt("Price rise flagged on the spot", 30, PALM, SEMIBOLD)).arrange(RIGHT, buff=0.25),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.38).next_to(right, DOWN, buff=0.7, aligned_edge=LEFT)
        self.play(FadeIn(reply[0], scale=0.7), run_time=0.35, rate_func=back)
        self.play(LaggedStart(*[FadeIn(l, shift=UP * 0.08) for l in reply_lines], lag_ratio=0.25), FadeIn(checks[0], shift=RIGHT * 0.3), run_time=1.1, rate_func=out)
        self.until(self.said(1, 0.55))
        self.play(FadeIn(checks[1], shift=RIGHT * 0.3), run_time=0.5, rate_func=out)

        self.until(self.said(2))
        self.play(chip.animate.set_opacity(1), FadeIn(checks[2], shift=RIGHT * 0.3), run_time=0.4, rate_func=out)
        self.play(Indicate(chip, color=GOLD, scale_factor=1.12), ok.animate.set_opacity(1), run_time=0.7)

    # 5 · costed to the plate
    def plate(self):
        step = VGroup(head("02", 28, GOLD), Line(ORIGIN, RIGHT * 0.8, color=GOLD, stroke_width=4)).arrange(RIGHT, buff=0.2)
        # two pieces rather than t2c, which lost the coloured word on this line
        title = VGroup(head("Every line, costed to the", 64, INK), head("plate.", 64, GOLD)).arrange(RIGHT, buff=0.28, aligned_edge=DOWN)
        top = VGroup(step, title).arrange(DOWN, aligned_edge=LEFT, buff=0.22).to_corner(UP + LEFT, buff=0.7)
        cols = [txt(s, 17, STONE, SEMIBOLD) for s in ["ON THE INVOICE", "RAW MATERIAL", "ON THE MENU"]]
        ys = [0.35, -0.6, -1.55, -2.5]
        srcs, mats = VGroup(), VGroup()
        for y, (a, p, m, u) in zip(ys, [("NIDO FCMP 2.5KG TIN", "47.00", "Milk powder", "18.80 / kg"), ("EVAP MILK 410G", "3.25", "Evaporated milk", "7.93 / l"),
                                         ("TEA DUST 1KG", "28.50", "Tea dust", "28.50 / kg"), ("SUGAR WHITE 10KG", "62.00", "Sugar", "6.20 / kg")]):
            box = card(3.9, 0.66, PAPER, 0.1, stroke=LINE_GREY).move_to([-4.95, y, 0])
            lab = mono(a, 15, INK).move_to(box).align_to(box, LEFT).shift(RIGHT * 0.2)
            pr = mono(p, 15, STONE).move_to(box).align_to(box, RIGHT).shift(LEFT * 0.2)
            srcs.add(VGroup(box, lab, pr))
            pill = card(3.2, 0.66, MIST, 0.1).move_to([-0.95, y, 0])
            ml = txt(m, 19, PALM, BOLD).move_to(pill).align_to(pill, LEFT).shift(RIGHT * 0.22)
            mu = txt(u, 14, STONE).move_to(pill).align_to(pill, RIGHT).shift(LEFT * 0.2)
            mats.add(VGroup(pill, ml, mu))
        cols[0].next_to(srcs, UP, buff=0.3, aligned_edge=LEFT)
        cols[1].next_to(mats, UP, buff=0.3, aligned_edge=LEFT)
        links = VGroup(*[Line(s.get_right(), m.get_left(), color=GOLD, stroke_width=4) for s, m in zip(srcs, mats)])

        dish = card(4.6, 4.45, PALM, 0.24).move_to([4.3, -1.1, 0])
        cols[2].next_to(dish, UP, buff=0.3, aligned_edge=LEFT)
        name = head("Karak chai", 36, CREAM)
        subl = txt("One cup · recipe on file", 16, SAGE)
        recs = VGroup(*[row(a, b, 3.8, 16, CREAM) for a, b in [("Evaporated milk 30 ml", "0.24"), ("Milk powder 5 g", "0.09"), ("Tea dust 3 g", "0.09"), ("Sugar 12 g", "0.07")]])
        for r in recs:
            r[1].set_color(CREAM)
        recs.arrange(DOWN, buff=0.12, aligned_edge=LEFT)
        dish_top = VGroup(name, subl, recs).arrange(DOWN, aligned_edge=LEFT, buff=0.14).move_to(dish).align_to(dish, UP).align_to(dish, LEFT).shift([0.4, -0.3, 0])
        recs.shift(DOWN * 0.1)

        self.play(FadeIn(top, shift=UP * 0.2), run_time=0.5, rate_func=out)
        self.until(self.said(0))
        self.play(FadeIn(cols[0]), LaggedStart(*[FadeIn(s, shift=RIGHT * 0.4) for s in srcs], lag_ratio=0.15), run_time=0.8, rate_func=out)
        self.play(LaggedStart(*[Create(l) for l in links], lag_ratio=0.15), FadeIn(cols[1]), run_time=0.7)
        self.play(LaggedStart(*[FadeIn(m, shift=RIGHT * 0.3) for m in mats], lag_ratio=0.15), run_time=0.7, rate_func=out)

        # each material flows into the recipe
        self.until(self.said(1))
        self.play(FadeIn(cols[2]), FadeIn(dish, shift=LEFT * 0.5), FadeIn(name), FadeIn(subl), run_time=0.5, rate_func=out)
        flows = []
        for m, r in zip(mats, [recs[1], recs[0], recs[2], recs[3]]):
            start, end = m.get_right(), r.get_left() + LEFT * 0.1
            path = CubicBezier(start, start + RIGHT * 1.0, end + LEFT * 1.0, end)
            dot = Dot(start, radius=0.09, color=GOLD)
            flows.append((dot, path))
        self.play(LaggedStart(*[MoveAlongPath(d, p, rate_func=smooth) for d, p in flows], lag_ratio=0.2), run_time=1.1)
        self.play(*[FadeOut(d, scale=0.3) for d, _ in flows], LaggedStart(*[FadeIn(r, shift=RIGHT * 0.15) for r in recs], lag_ratio=0.15), run_time=0.6)

        # the plate cost and what the cup keeps
        self.until(self.said(2))
        cost = ValueTracker(0)
        cost_row = always_redraw(lambda: VGroup(txt("Plate cost", 17, SAGE), head(f"AED {cost.get_value():.2f}", 30, CREAM)).arrange(RIGHT, buff=0.4).next_to(recs, DOWN, buff=0.25, aligned_edge=LEFT))
        self.play(FadeIn(cost_row), cost.animate.set_value(0.49), run_time=1.1, rate_func=out)
        kept = ValueTracker(0)
        ring_c = recs.get_left() + RIGHT * 0.45 + DOWN * 1.9
        ring = Annulus(inner_radius=0.3, outer_radius=0.44, fill_color="#2a5a4f", fill_opacity=1, stroke_width=0).move_to(ring_c)
        arc = always_redraw(lambda: AnnularSector(inner_radius=0.3, outer_radius=0.44, angle=-kept.get_value() / 100 * 6.2832, start_angle=1.5708,
                                                   fill_color=GOLD, fill_opacity=1, stroke_width=0, arc_center=ring_c))
        pct = always_redraw(lambda: head(f"{int(kept.get_value())}%", 17, CREAM).move_to(ring_c))
        note = VGroup(txt("Sells at AED 1.50", 15, SAGE), head("keeps 67%", 26, GOLD)).arrange(DOWN, aligned_edge=LEFT, buff=0.06).next_to(ring, RIGHT, buff=0.3)
        self.play(FadeIn(ring), FadeIn(note, shift=LEFT * 0.2), run_time=0.3)
        self.add(arc, pct)  # redrawn every frame, so they are added rather than faded
        self.play(kept.animate.set_value(67), run_time=1.1, rate_func=out)

    # 6 · the dashboard
    def dashboard(self):
        step = VGroup(head("03", 28, GOLD), Line(ORIGIN, RIGHT * 0.8, color=GOLD, stroke_width=4)).arrange(RIGHT, buff=0.2)
        title = head("Know what to push.", 64, INK, t2c={"push.": GOLD})
        top = VGroup(step, title).arrange(DOWN, aligned_edge=LEFT, buff=0.22).to_corner(UP + LEFT, buff=0.7)
        answer_box = card(12.6, 1.05, PALM, 0.2).move_to([0, 0.95, 0])
        answer = txt("Look at Deira: keeps 61%, the least of the three branches.", 28, CREAM, MEDIUM)
        answer.move_to(answer_box).align_to(answer_box, LEFT).shift(RIGHT * 0.75)
        dot = Dot(radius=0.07, color=GOLD).next_to(answer, LEFT, buff=0.25)

        left = card(6.1, 3.5, PAPER, 0.2).move_to([-3.25, -1.95, 0])
        right = card(6.1, 3.5, PAPER, 0.2).move_to([3.25, -1.95, 0])
        lt = txt("Branches · share kept", 20, INK, BOLD, "Manrope").move_to(left).align_to(left, UP).align_to(left, LEFT).shift([0.35, -0.3, 0])
        rt = txt("Dishes · what to push", 20, INK, BOLD, "Manrope").move_to(right).align_to(right, UP).align_to(right, LEFT).shift([0.35, -0.3, 0])

        bars, labels = VGroup(), VGroup()
        for i, (name, v, c) in enumerate([("Deira", 61, GOLD), ("Karama", 68, PALM), ("Al Quoz", 71, PALM)]):
            y = -1.25 - i * 0.8
            nm = txt(name, 20, INK).move_to([-5.7, y, 0]).align_to(lt, LEFT)
            track = card(3.4, 0.3, MIST, 0.15).move_to([-3.05, y, 0])
            bar = card(3.4 * v / 100, 0.3, c, 0.15).align_to(track, LEFT).move_to(track, coor_mask=[0, 1, 0])
            val = txt(f"{v}%", 20, INK, BOLD).next_to(track, RIGHT, buff=0.25)
            labels.add(VGroup(nm, track, val))
            bars.add(bar)

        dishes = VGroup()
        for i, (name, v, word, icon) in enumerate([("Karak chai", "keeps 67%", "push", up_icon(PALM, 0.17)),
                                                   ("Cheese paratha", "keeps 64%", "push", up_icon(PALM, 0.17)),
                                                   ("Chicken 65 Dry", "keeps 38%", "look at it", check_icon(GOLD, 0.17))]):
            if i == 2:
                icon = VGroup(Circle(radius=0.17, fill_color=GOLD, fill_opacity=1, stroke_width=0), txt("!", 16, PAPER, BOLD))
            y = -1.25 - i * 0.8
            nm = txt(name, 20, INK).move_to([1.0, y, 0]).align_to(rt, LEFT)
            val = txt(v, 17, STONE).move_to([3.0, y, 0]).align_to([3.05, 0, 0], LEFT)
            tag = VGroup(icon, txt(word, 17, PALM if i < 2 else CAUTION, BOLD)).arrange(RIGHT, buff=0.1).move_to([5.0, y, 0]).align_to([4.55, 0, 0], LEFT)
            dishes.add(VGroup(nm, val, tag))

        self.play(FadeIn(top, shift=UP * 0.2), run_time=0.5, rate_func=out)
        self.until(self.said(0))
        self.play(FadeIn(answer_box, scale=0.96), FadeIn(dot, scale=2), run_time=0.4, rate_func=out)
        self.play(Write(answer), run_time=1.3, rate_func=linear)

        self.until(self.said(1))
        self.play(FadeIn(left, shift=UP * 0.3), FadeIn(lt), run_time=0.4, rate_func=out)
        self.play(LaggedStart(*[FadeIn(l) for l in labels], lag_ratio=0.15), LaggedStart(*[GrowFromEdge(b, LEFT) for b in bars], lag_ratio=0.15), run_time=0.9, rate_func=out)
        self.play(Indicate(labels[0][0], color=CAUTION), Indicate(bars[0], color=GOLD, scale_factor=1.06), run_time=0.7)

        self.until(self.said(2))
        self.play(FadeIn(right, shift=UP * 0.3), FadeIn(rt), run_time=0.4, rate_func=out)
        self.play(LaggedStart(*[FadeIn(d, shift=LEFT * 0.2) for d in dishes], lag_ratio=0.25), run_time=1.0, rate_func=out)

    # 7 · the morning brief
    def brief(self):
        c = [-3.6, 0.2, 0]
        face = Circle(radius=1.6, fill_color=PALM_DEEP, fill_opacity=1, stroke_color=SAGE, stroke_width=4).move_to(c)
        ticks = VGroup(*[Line([0, 1.35, 0], [0, 1.5 if i % 3 else 1.2, 0], color=SAGE if i % 3 else GOLD, stroke_width=4 if i % 3 else 7).rotate(-i * 0.5236, about_point=ORIGIN).shift(c) for i in range(12)])
        hour = Line([0, 0, 0], [0, 0.85, 0], color=CREAM, stroke_width=10).shift(c).rotate(-5 * 0.5236, about_point=c)
        minute = Line([0, 0, 0], [0, 1.25, 0], color=GOLD, stroke_width=7).shift(c)
        hub = Dot(c, radius=0.1, color=CREAM)
        clock = VGroup(face, ticks, hour, minute, hub)
        heading = head("Every morning, 7:00.", 52, CREAM, t2c={"7:00.": GOLD}).next_to(clock, DOWN, buff=0.55)
        sub = txt("Your numbers, on the phone you already carry.", 22, SAGE).next_to(heading, DOWN, buff=0.22)
        heading.align_to([-6.3, 0, 0], LEFT)
        sub.align_to(heading, LEFT)

        ph = phone(title="Faida", subtitle="Daily brief").move_to([3.7, -0.05, 0])
        tiles = VGroup()
        for k, v, s in [("Sold on 23 Sep", "AED 6,420", None), ("Month so far", "AED 142,880", None), ("Materials share of costed sales", "34%", "covers 91% of sales")]:
            parts = [txt(k, 11, STONE, SEMIBOLD), head(v, 26, INK)] + ([txt(s, 10, STONE)] if s else [])
            inner = VGroup(*parts).arrange(DOWN, aligned_edge=LEFT, buff=0.04)
            box = card(2.35, inner.height + 0.26, PAPER, 0.1)
            inner.move_to(box).align_to(box, LEFT).shift(RIGHT * 0.15)
            tiles.add(VGroup(box, inner))
        tiles.arrange(DOWN, buff=0.1)
        brief_card = VGroup(txt("Tue 23 Sep · all branches", 11, STONE, SEMIBOLD), tiles).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        panel = card(brief_card.width + 0.3, brief_card.height + 0.3, CREAM, 0.14)
        brief_card.move_to(panel)
        msg = bubble(VGroup(VGroup(panel, brief_card), txt("Deira kept the least this month.", 11, INK), txt("07:00", 9, STONE)).arrange(DOWN, aligned_edge=LEFT, buff=0.1), pad=0.1)
        msg.align_to(ph.screen, DOWN).align_to(ph.screen, LEFT).shift(UP * 0.2 + RIGHT * 0.14)

        self.play(FadeIn(clock, scale=0.8), run_time=0.5, rate_func=out)
        self.until(self.said(0))
        self.play(FadeIn(heading, shift=UP * 0.25), minute.animate.rotate(-6.2832 * 2 + 0.0001, about_point=c),
                  hour.animate.rotate(-2 * 0.5236, about_point=c), run_time=1.6, rate_func=smooth)
        self.play(Indicate(hour, color=GOLD, scale_factor=1.0), run_time=0.4)

        self.until(self.said(1))
        self.play(FadeIn(sub, shift=UP * 0.2), FadeIn(ph, shift=UP * 2.5), run_time=0.6, rate_func=out)
        self.play(FadeIn(msg, shift=UP * 0.3, scale=0.9), run_time=0.45, rate_func=back)
        self.play(LaggedStart(*[Indicate(t, color=GOLD, scale_factor=1.04) for t in tiles], lag_ratio=0.3), run_time=1.0)

    # 8 · the close
    def close(self):
        lines = VGroup(*[head(s, 104, CREAM) for s in ["Every item.", "Every branch.", "Real margins."]]).arrange(DOWN, buff=0.28)
        lines[2].set_color(GOLD)
        s0 = self.sentences[0]
        span = s0["end"] - s0["start"]
        for i, l in enumerate(lines):
            self.until(s0["start"] + i * span / 3 - 0.05)
            self.play(FadeIn(l, shift=UP * 0.4, scale=1.08), run_time=0.45, rate_func=out)

        self.until(self.said(1) - 0.35)
        self.play(FadeOut(lines, shift=UP * 0.8), run_time=0.35, rate_func=rate_functions.ease_in_cubic)
        m = mark(reversed_=True).scale_to_fit_height(1.9)
        word = txt("faida", 160, CREAM, SEMIBOLD, "Manrope")
        lockup = VGroup(m, word).arrange(RIGHT, buff=0.45).shift(UP * 1.1)
        word.align_to(m, DOWN).shift(DOWN * 0.1)
        line = txt("Profit, in plain sight.", 46, SAGE, BOLD, "Manrope", t2c={"plain sight.": GOLD}).next_to(lockup, DOWN, buff=0.6)
        cta_t = txt("Private pilot now open for GCC cafeterias", 28, CREAM, SEMIBOLD)
        cta = VGroup(RoundedRectangle(corner_radius=0.38, width=cta_t.width + 0.9, height=0.8, stroke_color=GOLD, stroke_width=3, fill_opacity=0), cta_t)
        cta.next_to(line, DOWN, buff=0.7)
        fine = txt("Figures shown are illustrative.", 15, SAGE).set_opacity(0.6).to_edge(DOWN, buff=0.35)
        self.play(LaggedStart(*[FadeIn(t, shift=DOWN * 0.8, scale=0.4) for t in m], lag_ratio=0.25), run_time=0.8, rate_func=back)
        self.play(Write(word), run_time=0.6)
        self.play(FadeIn(line, shift=UP * 0.2), run_time=0.5, rate_func=out)
        self.play(FadeIn(cta, shift=UP * 0.2), FadeIn(fine), run_time=0.5, rate_func=out)
        self.until(TIMINGS["scenes"][-1]["duration"] - 0.9)
        black = Rectangle(width=16, height=9, fill_color="#000000", fill_opacity=1, stroke_width=0).set_opacity(0)
        self.add(black)
        self.play(black.animate.set_fill(opacity=1), run_time=0.85)
