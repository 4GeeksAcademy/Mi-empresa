FROM node:22-alpine

RUN apk add --no-cache bash

WORKDIR /app

COPY uis/website/package*.json ./website/
RUN cd website && npm ci

COPY uis/backoffice/package*.json ./backoffice/
RUN cd backoffice && npm ci

COPY uis/start.sh /app/start.sh
COPY uis/website ./website
COPY uis/backoffice ./backoffice
COPY docs/telemetry /docs/telemetry

RUN chmod +x /app/start.sh

EXPOSE 3000 3001

CMD ["bash", "/app/start.sh"]