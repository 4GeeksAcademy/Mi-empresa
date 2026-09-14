FROM node:22-alpine

RUN apk add --no-cache bash

WORKDIR /app

COPY website/package*.json ./website/
RUN cd website && npm install

COPY backoffice/package*.json ./backoffice/
RUN cd backoffice && npm ci

COPY start.sh /app/start.sh
COPY website ./website
COPY backoffice ./backoffice

RUN chmod +x /app/start.sh

EXPOSE 3000 3001

CMD ["bash", "/app/start.sh"]