.PHONY: run-gateway run-proxy build deps

deps:
	go mod tidy

build: deps
	go build -o bin/gateway ./cmd/gateway
	go build -o bin/proxy ./cmd/proxy

run-gateway: build
	./bin/gateway

run-proxy: build
	./bin/proxy
