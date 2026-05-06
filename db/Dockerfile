FROM postgres:16-alpine

COPY init/ /docker-entrypoint-initdb.d/
COPY docker-entrypoint-tls.sh /usr/local/bin/docker-entrypoint-tls.sh
RUN chmod +x /docker-entrypoint-initdb.d/*.sh || true
RUN chmod +x /usr/local/bin/docker-entrypoint-tls.sh

ENTRYPOINT ["docker-entrypoint-tls.sh"]
CMD ["postgres"]
