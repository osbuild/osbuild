use pyo3::prelude::*;

use osbuild::utility;

#[pyfunction(name = "copy_tree")]
fn utility_filesystem_copy_tree(src: &str, dst: &str) -> PyResult<i64> {
    Ok(utility::filesystem::copy_tree(src, dst).unwrap())
}

#[pymodule]
fn osbuild_py(py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add("__version__", "test")?;

    register_utility(py, m)?;

    Ok(())
}

fn register_utility(py: Python<'_>, parent: &PyModule) -> PyResult<()> {
    let module = PyModule::new(py, "utility")?;
    parent.add_submodule(module)?;

    register_utility_filesystem(py, module)?;

    Ok(())
}

fn register_utility_filesystem(py: Python<'_>, parent: &PyModule) -> PyResult<()> {
    let module = PyModule::new(py, "filesystem")?;
    parent.add_submodule(module)?;

    module.add_function(wrap_pyfunction!(utility_filesystem_copy_tree, module)?)?;

    Ok(())
}

#[cfg(test)]
mod test {
    #[test]
    fn dummy() {
        assert!(true);
    }
}
