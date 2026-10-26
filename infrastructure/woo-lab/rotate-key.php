<?php
// Explicit local incident remediation only. Never called by seed/serve/verify automatically.
if (!defined('WP_CLI') || !WP_CLI || wp_get_environment_type() !== 'local') {
    throw new RuntimeException('LAB_ROTATION_SCOPE');
}
$initial = json_decode(file_get_contents('/run/woo-lab/initial.json'), true, 512, JSON_THROW_ON_ERROR);
$old = json_decode(file_get_contents('/run/woo-lab/runtime-auth.json'), true, 512, JSON_THROW_ON_ERROR);
$reader = get_user_by('login', $initial['reader_user']);
if (!$reader || $reader->has_cap('edit_products') || $reader->has_cap('manage_options') || $reader->has_cap('manage_woocommerce') || empty($old['key_id']) || $old['key_permissions'] !== 'read') {
    throw new RuntimeException('LAB_ROTATION_BINDING');
}
// Bind the exact pair, owner, scope and key ID using pinned Woo's own lookup.
$lookup = new ReflectionMethod(WC_REST_Authentication::class, 'get_user_data_by_consumer_key');
$authentication = new WC_REST_Authentication();
$record = $lookup->invoke($authentication, $old['consumer_key']);
if (!$record || (int) $record->key_id !== (int) $old['key_id'] || (int) $record->user_id !== (int) $reader->ID || $record->permissions !== 'read' || !hash_equals($record->consumer_secret, $old['consumer_secret'])) {
    throw new RuntimeException('LAB_ROTATION_PAIR_MISMATCH');
}
// Invoke the pinned Woo implementation; do not reproduce its key-table SQL.
wp_set_current_user($reader->ID);
$revoke = new ReflectionMethod(WC_Auth::class, 'maybe_delete_key');
$revoke->invoke(new WC_Auth(), $old);
if ($lookup->invoke($authentication, $old['consumer_key'])) {
    throw new RuntimeException('LAB_ROTATION_REVOKE_FAILED');
}
class CommerceOps_Lab_Rotation_Issuer extends WC_Auth {
    public function issue() { return $this->create_keys('CommerceOps synthetic local reader rotated', 'commerceops_lab', 'read'); }
}
$auth = (new CommerceOps_Lab_Rotation_Issuer())->issue();
if (empty($auth['key_id']) || $auth['key_id'] === $old['key_id']) {
    throw new RuntimeException('LAB_ROTATION_CREATE');
}
echo json_encode($auth, JSON_THROW_ON_ERROR);
