FROM golang:1.21-alpine AS builder

WORKDIR /app

COPY go.mod ./
COPY go.sum ./

RUN go mod download

COPY . .

RUN go build -o /proxy ./cmd/proxy
RUN go build -o /gateway ./cmd/gateway

FROM alpine:latest

RUN apk --no-cache add ca-certificates

WORKDIR /root/

COPY --from=builder /proxy .
COPY --from=builder /gateway .

EXPOSE 8080

CMD ["./proxy"]
