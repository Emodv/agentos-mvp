FROM golang:1.23-alpine AS builder

WORKDIR /app

# Cache dependencies separately from source for faster rebuilds.
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /l2agent ./cmd/l2agent

FROM alpine:3.21

RUN apk --no-cache add ca-certificates && adduser -D -u 10001 app
USER app
WORKDIR /home/app

COPY --from=builder /l2agent .

EXPOSE 8080

CMD ["./l2agent", "serve"]
