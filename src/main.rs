//! documix entry point. mimalloc replaces the system allocator: the
//! converters allocate heavily from many threads, and macOS malloc scales
//! poorly there.
#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

fn main() {
    documix::cli::main();
}
