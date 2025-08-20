echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"
docker build -t "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA" .
docker push "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA"