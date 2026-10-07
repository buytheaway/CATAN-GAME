FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/index.html web/vite.config.ts web/tsconfig*.json web/postcss.config.cjs ./
COPY web/src/ ./src/
COPY web/public/ ./public/
RUN npm run build

FROM nginx:stable-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /web/dist/ /usr/share/nginx/html/
RUN chown -R nginx:nginx /var/cache/nginx
USER nginx
EXPOSE 8080
STOPSIGNAL SIGQUIT
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
