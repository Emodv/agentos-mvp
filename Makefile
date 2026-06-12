.PHONY: build test vet run gateway docker clean

build:
	go build -o bin/l2agent ./cmd/l2agent

test:
	go test ./...

vet:
	go vet ./...

run: build
	./bin/l2agent serve

gateway: build
	./bin/l2agent gateway

docker:
	docker build -t l2agent .

clean:
	rm -rf bin
