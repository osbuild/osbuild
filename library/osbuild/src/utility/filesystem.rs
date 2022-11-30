use std::io;
use std::path::Path;

use cap_std::ambient_authority;
use cap_std::fs::Dir;

/// Copy a tree from `src` to `dst`, returns the count of directories and files copied or an
/// io::Error.
pub fn copy_tree(src: impl AsRef<Path>, dst: impl AsRef<Path>) -> io::Result<i64> {
    let src_dir = Dir::open_ambient_dir(src, ambient_authority())?;
    let dst_dir = Dir::open_ambient_dir(dst, ambient_authority())?;

    let mut count = 0;

    Ok(count)
}
