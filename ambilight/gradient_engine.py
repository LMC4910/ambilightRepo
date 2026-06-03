import math
from typing import List, Tuple

def srgb_to_linear(c: float) -> float:
    c = c / 255.0
    if c <= 0.04045:
        return c / 12.92
    else:
        return math.pow((c + 0.055) / 1.055, 2.4)

def linear_to_srgb(c: float) -> int:
    if c <= 0.0031308:
        c = c * 12.92
    else:
        c = 1.055 * math.pow(c, 1 / 2.4) - 0.055
    c = max(0.0, min(1.0, c))
    return int(round(c * 255.0))

def rgb_to_oklab(r: int, g: int, b: int) -> Tuple[float, float, float]:
    lr = srgb_to_linear(r)
    lg = srgb_to_linear(g)
    lb = srgb_to_linear(b)

    l = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
    m = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
    s = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb

    l_ = math.cbrt(l) if l >= 0 else -math.cbrt(-l)
    m_ = math.cbrt(m) if m >= 0 else -math.cbrt(-m)
    s_ = math.cbrt(s) if s >= 0 else -math.cbrt(-s)

    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_ = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_

    return (L, a, b_)

def oklab_to_rgb(L: float, a: float, b_: float) -> Tuple[int, int, int]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b_
    m_ = L - 0.1055613458 * a - 0.0638541728 * b_
    s_ = L - 0.0894841775 * a - 1.2914855480 * b_

    l = l_ * l_ * l_
    m = m_ * m_ * m_
    s = s_ * s_ * s_

    lr =  4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    lb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    r = linear_to_srgb(lr)
    g = linear_to_srgb(lg)
    b = linear_to_srgb(lb)

    return (r, g, b)

def blend_oklab(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    """Blend two RGB colors using OKLab color space interpolation."""
    t = max(0.0, min(1.0, t))
    L1, a1, b1 = rgb_to_oklab(*c1)
    L2, a2, b2 = rgb_to_oklab(*c2)
    
    L = L1 + t * (L2 - L1)
    a = a1 + t * (a2 - a1)
    b_ = b1 + t * (b2 - b1)
    
    return oklab_to_rgb(L, a, b_)

def generate_linear_gradient(colors: List[Tuple[int, int, int]], steps: int) -> List[Tuple[int, int, int]]:
    """Generate a perceptually uniform gradient from a list of RGB colors."""
    if not colors:
        return [(0,0,0)] * steps
    if len(colors) == 1:
        return list(colors) * steps

    result = []
    num_segments = len(colors) - 1

    for i in range(steps):
        t_global = i / max(1, steps - 1)
        segment = min(num_segments - 1, int(t_global * num_segments))
        t_local = (t_global - (segment / num_segments)) * num_segments

        c1 = colors[segment]
        c2 = colors[segment + 1]

        result.append(blend_oklab(c1, c2, t_local))

    return result


def _mean_color(colors: List[Tuple[int, int, int]]) -> Tuple[int, int, int]:
    if not colors:
        return (0, 0, 0)
    n = len(colors)
    return (
        sum(c[0] for c in colors) // n,
        sum(c[1] for c in colors) // n,
        sum(c[2] for c in colors) // n,
    )


def generate_radial_gradient(colors: List[Tuple[int, int, int]], steps: int) -> List[Tuple[int, int, int]]:
    """Symmetric gradient: the strip mirrors around its centre (FR-GRAD-03).

    The mean colour anchors the centre and the supplied colours fan out toward
    both ends, so a strip lights symmetrically from the middle outward.
    """
    if not colors:
        return [(0, 0, 0)] * steps
    center = _mean_color(colors)
    # Build a half gradient (centre → edge) then mirror it.
    half = max(1, steps // 2)
    half_grad = generate_linear_gradient([center, colors[-1]], half)
    mirrored = list(reversed(half_grad)) + half_grad
    # Pad/trim to exactly `steps`.
    if len(mirrored) < steps:
        mirrored += [mirrored[-1]] * (steps - len(mirrored))
    return mirrored[:steps]


def generate_ambient_gradient(colors: List[Tuple[int, int, int]], steps: int) -> List[Tuple[int, int, int]]:
    """Calm wash that blends every zone toward the global mean (FR-GRAD-04)."""
    if not colors:
        return [(0, 0, 0)] * steps
    mean = _mean_color(colors)
    softened = [blend_oklab(c, mean, 0.5) for c in colors]
    return generate_linear_gradient(softened, steps)


def _apply_gamma(pixels: List[Tuple[int, int, int]], gamma: float) -> List[Tuple[int, int, int]]:
    """Optional extra gamma correction on the final pixel list (FR-GRAD-06)."""
    if not gamma or abs(gamma - 1.0) < 1e-3:
        return pixels
    inv = 1.0 / gamma
    lut = [int(round(((v / 255.0) ** inv) * 255.0)) for v in range(256)]
    return [(lut[r], lut[g], lut[b]) for (r, g, b) in pixels]


def generate_gradient(
    mode: str,
    colors: List[Tuple[int, int, int]],
    steps: int,
    gamma: float = 1.0,
) -> List[Tuple[int, int, int]]:
    """Dispatch to a gradient mode and apply optional gamma.

    Modes: ``linear`` | ``radial`` | ``ambient`` | ``screen_matched`` (the last
    maps the ordered perimeter zone colours straight onto the strip, same maths
    as ``linear``).
    """
    if mode == "radial":
        pixels = generate_radial_gradient(colors, steps)
    elif mode == "ambient":
        pixels = generate_ambient_gradient(colors, steps)
    else:  # linear / screen_matched
        pixels = generate_linear_gradient(colors, steps)
    return _apply_gamma(pixels, gamma)
