.PHONY: docker-preflight docker-build

docker-preflight:
	./scripts/docker-preflight.sh

docker-build: docker-preflight
	docker build -t swift-deploy-1-node:latest .