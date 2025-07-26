mkdir -p $BUILD_DIR
cd $BUILD_DIR
cmake $CMAKE_FLAGS ..
cd ..
find . -regex '.*\.\(cpp\|cc\)' -exec clang-tidy {} -- -I. \;