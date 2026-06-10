FROM golang:1.21-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git

COPY go.mod ./
RUN go mod tidy || true

COPY . .

RUN go mod tidy
RUN go build -o /proxy ./cmd/proxy
RUN go build -o /gateway ./cmd/gateway

FROM alpine:latest

RUN apk --no-cache add ca-certificates

WORKDIR /root/

COPY --from=builder /proxy .
COPY --from=builder /gateway .
COPY --from=builder /app/dashboard ./dashboard

EXPOSE 8080

CMD ["./proxy"]
