# syntax=docker/dockerfile:1.7
FROM wordpress:7.1.3-php8.3-apache@sha256:d42f63cb89ad0eab272c4b393164e63830d0df270009907919f7dcce52b1a20b
ADD --checksum=sha256:ce34ddd838f7351d6759068d09793f26755463b4a4610a5a5c0a97b68220d85c https://github.com/wp-cli/wp-cli/releases/download/v2.12.0/wp-cli-2.12.0.phar /usr/local/bin/wp
ADD --checksum=sha256:5317434cb381b5fdc7c1dd6ee258324f08c390976aaf8d1199f2a0e9a3ab8586 https://downloads.wordpress.org/plugin/woocommerce.11.2.1.zip /opt/woo-lab/woocommerce.zip
RUN chmod 0755 /usr/local/bin/wp \
 && php -r '$z=new ZipArchive(); if($z->open("/opt/woo-lab/woocommerce.zip")!==true || !$z->extractTo("/usr/src/wordpress/wp-content/plugins")){exit(1);} $z->close();' \
 && rm /opt/woo-lab/woocommerce.zip \
 && mkdir -p /usr/src/wordpress/wp-content/mu-plugins \
 && sed -i 's/CustomLog ${APACHE_LOG_DIR}\/access.log combined/CustomLog \/dev\/null combined/' /etc/apache2/sites-available/000-default.conf
COPY infrastructure/woo-lab/lockdown.php /usr/src/wordpress/wp-content/mu-plugins/commerceops-lab.php
COPY infrastructure/woo-lab/bootstrap.php infrastructure/woo-lab/seed.php infrastructure/woo-lab/safety.php /opt/woo-lab/
