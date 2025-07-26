mkdir -p $BUILD_DIR
cd $BUILD_DIR
cmake $CMAKE_FLAGS ..
make -j$(nproc)