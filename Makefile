.PHONY: docker-preflight docker-build docker-build-host

docker-preflight:
	./scripts/docker-preflight.sh

docker-build: docker-preflight
	docker build -t swift-deploy-1-node:latest .

docker-build-host:
	docker build --network=host -t swift-deploy-1-node:latest .