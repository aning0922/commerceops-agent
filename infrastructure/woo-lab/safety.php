<?php
$http = wp_remote_get('https://example.com/commerceops-block-test', ['timeout' => 2]);
$mail = wp_mail('synthetic@example.invalid', 'Blocked synthetic probe', 'No external mail is allowed.');
$errno = 0; $errstr = '';
$socket = @stream_socket_client('tcp://1.1.1.1:443', $errno, $errstr, 2);
$tcp_blocked = ($socket === false);
if ($socket) { fclose($socket); }
$result = [
    'mail_rejected' => ($mail === false),
    'http_rejected' => is_wp_error($http) && $http->get_error_code() === 'commerceops_lab_egress_disabled',
    'external_tcp_blocked' => $tcp_blocked,
    'payment_gateways_empty' => empty(WC()->payment_gateways()->get_available_payment_gateways()),
    'webhook_delivery_rejected' => apply_filters('woocommerce_webhook_should_deliver', true) === false,
    'cron_disabled' => defined('DISABLE_WP_CRON') && DISABLE_WP_CRON,
    'async_scheduler_rejected' => apply_filters('action_scheduler_allow_async_request_runner', true) === false,
    'scheduled_queue_callback_absent' => !has_action('action_scheduler_run_queue'),
];
echo json_encode($result);
if (in_array(false, $result, true)) { exit(4); }
