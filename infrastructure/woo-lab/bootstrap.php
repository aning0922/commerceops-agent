<?php
// Only used by the owner-scoped CLI, never installed as a public endpoint.
$c = json_decode(file_get_contents('/run/woo-lab/initial.json'), true, 512, JSON_THROW_ON_ERROR);
$_SERVER['HTTP_HOST'] = parse_url($c['url'], PHP_URL_HOST).':'.parse_url($c['url'], PHP_URL_PORT);
$_SERVER['HTTPS'] = 'on';
define('WP_INSTALLING', true);
require '/var/www/html/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/upgrade.php';
require_once ABSPATH . 'wp-admin/includes/plugin.php';
if (!is_blog_installed()) {
    wp_install('CommerceOps synthetic local lab', $c['admin_user'], 'lab-admin@example.invalid', false, '', $c['admin_password']);
}
update_option('home', $c['url']);
update_option('siteurl', $c['url']);
update_option('timezone_string', 'Asia/Shanghai');
update_option('woocommerce_currency', 'CNY');
update_option('woocommerce_price_num_decimals', 2);
update_option('woocommerce_calc_taxes', 'no');
update_option('woocommerce_manage_stock', 'yes');
update_option('woocommerce_hold_stock_minutes', '');
update_option('woocommerce_enable_guest_checkout', 'yes');
update_option('blog_public', 0);
update_option('permalink_structure', '/%postname%/');
$r = activate_plugin('woocommerce/woocommerce.php');
if (is_wp_error($r)) { throw new RuntimeException('LAB_PLUGIN_ACTIVATION'); }
flush_rewrite_rules(true);
echo json_encode(['installed' => true, 'permalink_structure' => get_option('permalink_structure')]);
