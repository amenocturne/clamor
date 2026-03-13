/// Generate `n` perceptually uniform colors using OKLCH color space.
/// Returns a vec of color objects with `a` and `rgb` fields.
pub fn generate_colors(n: usize) -> Vec<ColorValue> {
    (0..n)
        .map(|i| {
            let hue = (i as f64 / n as f64) * 360.0;
            let (r, g, b) = oklch_to_srgb(0.75, 0.12, hue);
            let rgb_int = (r as u32) << 16 | (g as u32) << 8 | b as u32;
            ColorValue { a: 1, rgb: rgb_int }
        })
        .collect()
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ColorValue {
    pub a: u32,
    pub rgb: u32,
}

fn oklch_to_srgb(lightness: f64, chroma: f64, hue_deg: f64) -> (u8, u8, u8) {
    let hue_rad = hue_deg.to_radians();
    let a = chroma * hue_rad.cos();
    let b = chroma * hue_rad.sin();

    // OKLAB -> linear RGB via intermediate LMS
    let l_ = lightness + 0.3963377774 * a + 0.2158037573 * b;
    let m_ = lightness - 0.1055613458 * a - 0.0638541728 * b;
    let s_ = lightness - 0.0894841775 * a - 1.2914855480 * b;

    let l = l_ * l_ * l_;
    let m = m_ * m_ * m_;
    let s = s_ * s_ * s_;

    let r_lin = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
    let g_lin = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
    let b_lin = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s;

    (
        linear_to_srgb(r_lin),
        linear_to_srgb(g_lin),
        linear_to_srgb(b_lin),
    )
}

fn linear_to_srgb(value: f64) -> u8 {
    let c = if value <= 0.0031308 {
        12.92 * value
    } else {
        1.055 * value.powf(1.0 / 2.4) - 0.055
    };
    (c * 255.0).round().clamp(0.0, 255.0) as u8
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_correct_count() {
        let colors = generate_colors(5);
        assert_eq!(colors.len(), 5);
        for c in &colors {
            assert_eq!(c.a, 1);
        }
    }

    #[test]
    fn colors_are_distinct() {
        let colors = generate_colors(10);
        let rgbs: Vec<u32> = colors.iter().map(|c| c.rgb).collect();
        let unique: std::collections::HashSet<u32> = rgbs.iter().copied().collect();
        assert_eq!(unique.len(), rgbs.len());
    }

    #[test]
    fn srgb_clamps_negative() {
        assert_eq!(linear_to_srgb(-1.0), 0);
    }

    #[test]
    fn srgb_clamps_above_one() {
        assert_eq!(linear_to_srgb(2.0), 255);
    }
}
