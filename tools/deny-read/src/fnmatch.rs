/// fnmatch-style matching. Supports `*`, `?`, `[...]`, and `**` for recursive.
pub fn fnmatch(name: &str, pattern: &str) -> bool {
    fnmatch_inner(name.as_bytes(), pattern.as_bytes())
}

fn fnmatch_inner(name: &[u8], pattern: &[u8]) -> bool {
    let mut ni = 0;
    let mut pi = 0;
    let mut star_pi = None::<usize>; // position in pattern after last '*'
    let mut star_ni = 0usize; // position in name when we hit last '*'

    while ni < name.len() {
        if pi < pattern.len() {
            // Handle ** (matches path separators too)
            if pi + 1 < pattern.len() && pattern[pi] == b'*' && pattern[pi + 1] == b'*' {
                // Consume all consecutive * characters
                let mut pp = pi;
                while pp < pattern.len() && pattern[pp] == b'*' {
                    pp += 1;
                }
                // Skip a trailing slash after ** (so a/**/b matches a/b)
                if pp < pattern.len() && pattern[pp] == b'/' {
                    pp += 1;
                }
                // If rest of pattern is empty, match everything
                if pp >= pattern.len() {
                    return true;
                }
                // Try matching rest of pattern at every position in name.
                for start in ni..=name.len() {
                    if fnmatch_inner(&name[start..], &pattern[pp..]) {
                        return true;
                    }
                }
                return false;
            }

            match pattern[pi] {
                b'?' => {
                    if name[ni] != b'/' {
                        ni += 1;
                        pi += 1;
                        continue;
                    }
                }
                b'*' => {
                    star_pi = Some(pi + 1);
                    star_ni = ni;
                    pi += 1;
                    continue;
                }
                b'[' => {
                    if let Some((matched, end_pi)) = match_bracket(name[ni], &pattern[pi..]) {
                        if matched {
                            ni += 1;
                            pi += end_pi;
                            continue;
                        }
                    }
                }
                c => {
                    if c == name[ni] {
                        ni += 1;
                        pi += 1;
                        continue;
                    }
                }
            }
        }

        // Current chars don't match. Backtrack to last '*' if possible.
        if let Some(sp) = star_pi {
            if name[star_ni] == b'/' {
                return false;
            }
            star_ni += 1;
            ni = star_ni;
            pi = sp;
            continue;
        }

        return false;
    }

    // Remaining pattern must be all *'s (or empty)
    while pi < pattern.len() && pattern[pi] == b'*' {
        pi += 1;
    }

    pi >= pattern.len()
}

/// Match a bracket expression `[...]` against a character.
/// Returns Some((matched, bytes_consumed)) or None if malformed.
fn match_bracket(ch: u8, pattern: &[u8]) -> Option<(bool, usize)> {
    if pattern.is_empty() || pattern[0] != b'[' {
        return None;
    }
    let mut i = 1;
    let negate = if i < pattern.len() && (pattern[i] == b'!' || pattern[i] == b'^') {
        i += 1;
        true
    } else {
        false
    };

    let mut matched = false;
    let mut first = true;

    while i < pattern.len() {
        if pattern[i] == b']' && !first {
            let result = if negate { !matched } else { matched };
            return Some((result, i + 1));
        }
        first = false;

        // Range: a-z
        if i + 2 < pattern.len() && pattern[i + 1] == b'-' && pattern[i + 2] != b']' {
            let lo = pattern[i];
            let hi = pattern[i + 2];
            if ch >= lo && ch <= hi {
                matched = true;
            }
            i += 3;
        } else {
            if pattern[i] == ch {
                matched = true;
            }
            i += 1;
        }
    }

    None // Malformed: no closing ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic() {
        assert!(fnmatch("foo.txt", "*.txt"));
        assert!(fnmatch("foo.txt", "foo.*"));
        assert!(fnmatch("foo.txt", "foo.txt"));
        assert!(!fnmatch("foo.txt", "bar.txt"));
        assert!(!fnmatch("foo.txt", "*.rs"));
    }

    #[test]
    fn test_star_no_slash() {
        assert!(!fnmatch("dir/foo.txt", "*.txt"));
        assert!(fnmatch("dir/foo.txt", "dir/*.txt"));
    }

    #[test]
    fn test_doublestar() {
        assert!(fnmatch("a/b/c/foo.txt", "a/**/foo.txt"));
        assert!(fnmatch("a/foo.txt", "a/**/foo.txt"));
        assert!(fnmatch("secrets/deep/nested/key.pem", "secrets/**"));
        assert!(fnmatch("/project/secrets/key.pem", "/project/secrets/**"));
    }

    #[test]
    fn test_question_mark() {
        assert!(fnmatch("foo.txt", "fo?.txt"));
        assert!(!fnmatch("fooo.txt", "fo?.txt"));
    }

    #[test]
    fn test_bracket() {
        assert!(fnmatch("foo.txt", "foo.[tx][xo][ta]"));
        assert!(fnmatch("a", "[abc]"));
        assert!(!fnmatch("d", "[abc]"));
        assert!(fnmatch("d", "[!abc]"));
    }
}
