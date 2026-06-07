FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o bin/gateway ./cmd/gateway
RUN go build -o bin/proxy ./cmd/proxy

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/bin/gateway .
COPY --from=builder /app/bin/proxy .
EXPOSE 8080
CMD ["./proxy"]
