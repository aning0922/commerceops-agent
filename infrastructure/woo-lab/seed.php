<?php
// Synthetic platform CRUD only. No direct SQL for products/orders/refunds.
$spec = json_decode(file_get_contents('/opt/woo-lab/seed.json'), true, 512, JSON_THROW_ON_ERROR);
$initial = json_decode(file_get_contents('/run/woo-lab/initial.json'), true, 512, JSON_THROW_ON_ERROR);
if (WC_VERSION !== '11.2.1' || get_bloginfo('version') !== '7.1.3') { throw new RuntimeException('LAB_VERSION_MISMATCH'); }
if (get_option('commerceops_lab_spec_hash') && get_option('commerceops_lab_spec_hash') !== hash_file('sha256', '/opt/woo-lab/seed.json')) {
    throw new RuntimeException('LAB_SEED_VERSION_CHANGED');
}
global $registry;
$registry = get_option('commerceops_lab_objects_v1', ['products' => [], 'orders' => [], 'refunds' => []]);
$first = empty($registry['complete']);
function remember_lab($kind, $key, $id) {
    global $registry;
    $registry[$kind][$key] = $id;
    update_option('commerceops_lab_objects_v1', $registry, false);
}
function lab_date($value) {
    $d = new WC_DateTime($value);
    return $d;
}
foreach ($spec['products'] as $row) {
    $key = $row['key'];
    if (!isset($registry['products'][$key])) {
        $found = get_posts(['post_type' => ['product', 'product_variation'], 'post_status' => 'any', 'numberposts' => 2,
            'meta_key' => '_commerceops_lab_key', 'meta_value' => $key, 'fields' => 'ids']);
        if (count($found) > 1) { throw new RuntimeException('LAB_DUPLICATE_LOGICAL_PRODUCT'); }
        if ($found) { remember_lab('products', $key, (int) $found[0]); }
    }
    if (isset($registry['products'][$key])) {
        $p = wc_get_product($registry['products'][$key]);
        if (!$p || $p->get_meta('_commerceops_lab_key') !== $key) { throw new RuntimeException('LAB_PRODUCT_BINDING'); }
    } else {
        if ($row['type'] === 'variable') { $p = new WC_Product_Variable(); }
        elseif ($row['type'] === 'variation') { $p = new WC_Product_Variation(); }
        else { $p = new WC_Product_Simple(); }
        $p->set_name($row['name']);
        $p->set_sku($row['sku']);
        $p->set_status('publish');
        $p->set_catalog_visibility('visible');
        $p->set_regular_price($row['price']);
        $p->set_tax_status('none');
        $p->set_virtual(true);
        $p->set_manage_stock($row['manage_stock']);
        $p->set_backorders($row['backorders'] ?? 'no');
        if ($row['manage_stock']) { $p->set_stock_quantity($row['stock_quantity']); }
        $p->set_stock_status($row['stock_status']);
        if ($row['type'] === 'variable') {
            $attribute = new WC_Product_Attribute();
            $attribute->set_name('Color'); $attribute->set_options(['red', 'blue']);
            $attribute->set_visible(true); $attribute->set_variation(true);
            $p->set_attributes([$attribute]);
        }
        if ($row['type'] === 'variation') {
            $p->set_parent_id($registry['products'][$row['parent']]);
            $p->set_attributes(['color' => $row['color']]);
        }
        $p->update_meta_data('_commerceops_lab_key', $key);
        $p->set_date_created(lab_date($spec['created_at']));
        $p->save(); remember_lab('products', $key, $p->get_id());
    }
}
foreach ($spec['orders'] as $row) {
    $key = $row['key'];
    if (!isset($registry['orders'][$key])) {
        $candidates = wc_get_orders(['limit' => 100, 'orderby' => 'id', 'order' => 'ASC']);
        $found = [];
        foreach ($candidates as $candidate) {
            if ($candidate->get_meta('_commerceops_lab_key') === $key) { $found[] = $candidate->get_id(); }
        }
        if (count($found) > 1) { throw new RuntimeException('LAB_DUPLICATE_LOGICAL_ORDER'); }
        if ($found) { remember_lab('orders', $key, (int) $found[0]); }
    }
    if (!isset($registry['orders'][$key])) {
        $o = wc_create_order(['status' => 'pending', 'created_via' => 'commerceops_synthetic_lab']);
        if (is_wp_error($o)) { throw new RuntimeException('LAB_ORDER_CREATE'); }
        $o->set_currency('CNY'); $o->set_prices_include_tax(false);
        $o->set_billing_email('synthetic-buyer@example.invalid');
        $o->set_payment_method('synthetic_manual');
        $o->set_date_created(lab_date($row['created_at']));
        foreach ($row['lines'] as $line) {
            $p = wc_get_product($registry['products'][$line['product']]);
            $o->add_product($p, $line['quantity'], ['subtotal' => $line['total'], 'total' => $line['total']]);
        }
        $o->update_meta_data('_commerceops_lab_key', $key);
        $o->calculate_totals(false); $o->save();
        remember_lab('orders', $key, $o->get_id());
        $o->set_status($row['status']);
        if (in_array($row['status'], ['processing', 'completed'], true)) { $o->set_date_paid(lab_date($row['created_at'])); }
        if ($row['status'] === 'completed') { $o->set_date_completed(lab_date($row['created_at'])); }
        $o->save();
    }
}
foreach ($spec['refunds'] as $row) {
    $key = $row['key']; $o = wc_get_order($registry['orders'][$row['order']]);
    if (!isset($registry['refunds'][$key])) {
        foreach ($o->get_refunds() as $r) {
            if ($r->get_meta('_commerceops_lab_key') === $key) { remember_lab('refunds', $key, $r->get_id()); }
        }
    }
    if (!isset($registry['refunds'][$key])) {
        $lines = [];
        if ($row['quantity'] !== null) {
            $items = $o->get_items(); $id = array_key_first($items);
            $lines[$id] = ['qty' => $row['quantity'], 'refund_total' => $row['amount'], 'refund_tax' => []];
        }
        $r = wc_create_refund(['order_id' => $o->get_id(), 'amount' => $row['amount'], 'reason' => 'synthetic fixture '.$key,
            'line_items' => $lines, 'refund_payment' => false, 'restock_items' => false]);
        if (is_wp_error($r)) { throw new RuntimeException('LAB_REFUND_CREATE'); }
        $r->update_meta_data('_commerceops_lab_key', $key);
        $r->set_date_created(lab_date($row['created_at'])); $r->save();
        remember_lab('refunds', $key, $r->get_id());
    }
}
// Legitimate product CRUD sets the final synthetic inventory after order hooks.
// Refunds explicitly did NOT restock. Re-seeding a complete shop never resets stock.
if ($first) {
    foreach ($spec['products'] as $row) {
        if ($row['manage_stock']) {
            $p = wc_get_product($registry['products'][$row['key']]);
            $p->set_stock_quantity($row['stock_quantity']); $p->set_stock_status($row['stock_status']); $p->save();
        }
        if ($row['type'] === 'variable') { WC_Product_Variable::sync($registry['products'][$row['key']]); }
    }
}
add_role('commerceops_reader', 'CommerceOps lab reader', ['read' => true, 'read_private_products' => true,
    'read_private_shop_orders' => true, 'read_shop_order' => true, 'view_woocommerce_reports' => true]);
$user = get_user_by('login', $initial['reader_user']);
if (!$user) {
    $id = wp_insert_user(['user_login' => $initial['reader_user'], 'user_pass' => $initial['reader_password'],
        'user_email' => 'lab-reader@example.invalid', 'role' => 'commerceops_reader']);
    if (is_wp_error($id)) { throw new RuntimeException('LAB_READER_CREATE'); }
    $user = get_user_by('id', $id);
}
if ($user->has_cap('edit_products') || $user->has_cap('manage_options') || $user->has_cap('manage_woocommerce')) {
    throw new RuntimeException('LAB_READER_OVERPRIVILEGED');
}
if (file_exists('/run/woo-lab/runtime-auth.json')) {
    $auth = json_decode(file_get_contents('/run/woo-lab/runtime-auth.json'), true, 512, JSON_THROW_ON_ERROR);
    if (!get_option('commerceops_lab_key_issued')) { throw new RuntimeException('LAB_KEY_BINDING'); }
} else {
    if (get_option('commerceops_lab_key_issued')) { throw new RuntimeException('LAB_KEY_FILE_MISSING'); }
    // Use pinned Woo's own protected initialization hook; no hand-written key SQL.
    class CommerceOps_Lab_Key_Issuer extends WC_Auth {
        public function issue() { return $this->create_keys('CommerceOps synthetic local reader', 'commerceops_lab', 'read'); }
    }
    wp_set_current_user($user->ID);
    $auth = (new CommerceOps_Lab_Key_Issuer())->issue();
    if (empty($auth['key_id'])) { throw new RuntimeException('LAB_KEY_CREATE'); }
    update_option('commerceops_lab_key_issued', true, false);
}
$registry['complete'] = true;
update_option('commerceops_lab_objects_v1', $registry, false);
update_option('commerceops_lab_spec_hash', hash_file('sha256', '/opt/woo-lab/seed.json'), false);
$mapping = ['products' => [], 'orders' => [], 'refunds' => []];
foreach ($registry['products'] as $key => $id) { $mapping['products'][$key] = $id; }
foreach ($registry['orders'] as $key => $id) {
    $o = wc_get_order($id); $items = [];
    foreach ($o->get_items() as $item) { $items[] = ['id' => $item->get_id(), 'product_id' => $item->get_product_id(), 'variation_id' => $item->get_variation_id(), 'quantity' => $item->get_quantity(), 'total' => $item->get_total()]; }
    $mapping['orders'][$key] = ['id' => $id, 'status' => $o->get_status(), 'total' => $o->get_total(), 'lines' => $items];
}
$mapping['refunds'] = $registry['refunds'];
echo json_encode(['runtime_auth' => $auth, 'mapping' => $mapping, 'versions' => ['wordpress' => get_bloginfo('version'), 'woocommerce' => WC_VERSION, 'php' => PHP_VERSION],
    'reader_caps' => ['read_private_products' => $user->has_cap('read_private_products'), 'read_private_shop_orders' => $user->has_cap('read_private_shop_orders'), 'edit_products' => false, 'manage_options' => false, 'manage_woocommerce' => false],
    'seed_complete' => true, 'clock' => $spec['clock'], 'timezone' => get_option('timezone_string'), 'currency' => get_option('woocommerce_currency')]);
