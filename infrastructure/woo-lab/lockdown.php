<?php
/** Plugin Name: CommerceOps isolated synthetic lab guard */
if (!defined('ABSPATH')) { exit; }
add_filter('pre_wp_mail', static function () { return false; });
add_filter('pre_http_request', static function () {
    return new WP_Error('commerceops_lab_egress_disabled', 'External HTTP disabled in synthetic lab.');
}, PHP_INT_MAX);
add_filter('woocommerce_webhook_should_deliver', '__return_false', PHP_INT_MAX);
add_filter('action_scheduler_allow_async_request_runner', '__return_false', PHP_INT_MAX);
add_action('init', static function () {
    remove_all_actions('action_scheduler_run_queue');
}, PHP_INT_MAX);
add_filter('woocommerce_allow_tracking', '__return_false');
add_filter('woocommerce_admin_features', '__return_empty_array');
add_filter('auto_update_plugin', '__return_false');

add_filter('woocommerce_available_payment_gateways', '__return_empty_array', PHP_INT_MAX);
add_filter('woocommerce_payment_gateways', '__return_empty_array', PHP_INT_MAX);
