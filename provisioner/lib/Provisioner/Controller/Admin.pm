package Provisioner::Controller::Admin;
use Mojo::Base 'Mojolicious::Controller', -signatures;

my @VENDORS = qw(yealink polycom);

my %VENDOR_TEMPLATE = (
    yealink => 'config/yealink',
    polycom => 'config/polycom_phone',
);

my %DEFAULT_ATTRIBUTES = (
    yealink => sub ($d) {
        my $user = $d->{sip_user} || $d->{extension} || '';
        my $name = $d->{display_name} || $d->{label}
          || $d->{extension} || $d->{mac};
        return (
            'account.1.enable'              => 1,
            'account.1.label'                => $name,
            'account.1.display_name'         => $name,
            'account.1.user_name'            => $user,
            'account.1.auth_name'            => $user,
            'account.1.password'             => $d->{sip_password} || '',
            'account.1.sip_server.1.address' => $d->{sip_server} || '',
            'account.1.sip_server.1.port'    => $d->{sip_port} || 5060,
        );
    },
    polycom => sub ($d) {
        my $user = $d->{sip_user} || $d->{extension} || '';
        my $name = $d->{display_name} || $d->{label}
          || $d->{extension} || $d->{mac};
        return (
            'reg.1.address'          => $user,
            'reg.1.auth.userId'      => $user,
            'reg.1.auth.password'    => $d->{sip_password} || '',
            'reg.1.displayName'      => $name,
            'reg.1.label'            => $name,
            'reg.1.line.1.label'     => "Ext. " . ($d->{extension} || ''),
            'reg.1.server.1.address' => $d->{sip_server} || '',
            'reg.1.server.1.port'    => $d->{sip_port} || 5060,
        );
    },
);

sub index ($self) {
    my $q = $self->param('q') // '';

    my $devices =
      length($q)
      ? $self->mysql->db->query(
          'SELECT * FROM devices
               WHERE mac LIKE ? OR label LIKE ?
                  OR extension LIKE ? OR display_name LIKE ?
               ORDER BY created_at DESC',
          ("%$q%") x 4
        )->hashes
      : $self->mysql->db->query(
          'SELECT * FROM devices ORDER BY created_at DESC'
        )->hashes;

    return $self->render(
        template => 'admin/devices/index',
        layout   => 'admin',
        devices  => $devices,
        q        => $q,
    );
}

sub new_form ($self) {
    return $self->render(
        template => 'admin/devices/form',
        layout   => 'admin',
        device   => {},
        vendors  => \@VENDORS,
        action   => '/admin/devices',
        error    => undef,
    );
}

sub edit_form ($self) {
    my $device = $self->_find_or_404($self->stash('mac')) or return;

    return $self->render(
        template => 'admin/devices/form',
        layout   => 'admin',
        device   => $device,
        vendors  => \@VENDORS,
        action   => "/admin/devices/$device->{mac}",
        error    => undef,
    );
}

sub create ($self) {
    my $mac = $self->normalize_mac($self->param('mac'));

    return $self->_form_error('Invalid MAC address', {}, '/admin/devices')
      unless $mac;

    my $fields = $self->_device_params;

    eval {
        $self->mysql->db->query(
            'INSERT INTO devices
                 (mac, vendor, model, label, extension, display_name,
                  sip_server, sip_port, sip_user, sip_password)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            $mac,               $fields->{vendor},
            $fields->{model},   $fields->{label},
            $fields->{extension}, $fields->{display_name},
            $fields->{sip_server}, $fields->{sip_port},
            $fields->{sip_user}, $fields->{sip_password},
        );
        1;
    } or do {
        my $err = $@;
        $fields->{mac} = $mac;
        return $self->_form_error(
            "Could not save device: $err", $fields, '/admin/devices'
        );
    };

    $fields->{mac} = $mac;
    $self->_generate_default_attributes($fields);

    return $self->redirect_to("/admin/devices/$mac");
}

sub update ($self) {
    my $mac = $self->stash('mac');
    $self->_find_or_404($mac) or return;

    my $fields = $self->_device_params;

    eval {
        $self->mysql->db->query(
            'UPDATE devices SET
                 vendor = ?, model = ?, label = ?, extension = ?,
                 display_name = ?, sip_server = ?, sip_port = ?,
                 sip_user = ?, sip_password = ?
             WHERE mac = ?',
            $fields->{vendor},     $fields->{model},
            $fields->{label},      $fields->{extension},
            $fields->{display_name}, $fields->{sip_server},
            $fields->{sip_port},   $fields->{sip_user},
            $fields->{sip_password}, $mac,
        );
        1;
    } or do {
        my $err = $@;
        $fields->{mac} = $mac;
        return $self->_form_error(
            "Could not save device: $err", $fields, "/admin/devices/$mac"
        );
    };

    return $self->redirect_to("/admin/devices/$mac");
}

sub destroy ($self) {
    my $mac = $self->stash('mac');
    $self->_find_or_404($mac) or return;

    $self->mysql->db->query('DELETE FROM devices WHERE mac = ?', $mac);

    return $self->redirect_to('/admin/devices');
}

sub show ($self) {
    my $device = $self->_find_or_404($self->stash('mac')) or return;

    my $requests = $self->mysql->db->query(
        'SELECT path, remote_addr, user_agent, matched, created_at
             FROM provisioning_requests
             WHERE mac = ?
             ORDER BY created_at DESC
             LIMIT 20',
        $device->{mac}
    )->hashes;

    my $attributes = $self->mysql->db->query(
        'SELECT attr_key, attr_value FROM device_attributes
             WHERE mac = ? ORDER BY attr_key',
        $device->{mac}
    )->hashes;

    my $template = $VENDOR_TEMPLATE{ $device->{vendor} };

    my $rendered_config =
      $template
      ? $self->render_to_string(
          template   => $template,
          format     => 'cfg',
          device     => $device,
          attributes => $attributes,
        )
      : undef;

    return $self->render(
        template   => 'admin/devices/show',
        format     => 'html',
        layout     => 'admin',
        device     => $device,
        requests   => $requests,
        attributes => $attributes,
        config     => $rendered_config,
    );
}

sub add_attribute ($self) {
    my $mac = $self->stash('mac');
    $self->_find_or_404($mac) or return;

    my $key = $self->param('attr_key') // '';
    my $value = $self->param('attr_value') // '';

    if (length $key) {
        $self->mysql->db->query(
            'INSERT INTO device_attributes (mac, attr_key, attr_value)
                 VALUES (?, ?, ?)
             ON DUPLICATE KEY UPDATE attr_value = VALUES(attr_value)',
            $mac, $key, $value
        );
    }

    return $self->redirect_to("/admin/devices/$mac");
}

sub delete_attribute ($self) {
    my $mac = $self->stash('mac');
    $self->_find_or_404($mac) or return;

    $self->mysql->db->query(
        'DELETE FROM device_attributes WHERE mac = ? AND attr_key = ?',
        $mac, $self->stash('key')
    );

    return $self->redirect_to("/admin/devices/$mac");
}

sub _device_params ($self) {
    return {
        vendor       => $self->param('vendor') // '',
        model        => $self->param('model') // '',
        label        => $self->param('label') // '',
        extension    => $self->param('extension') // '',
        display_name => $self->param('display_name') // '',
        sip_server   => $self->param('sip_server') // '',
        sip_port     => $self->param('sip_port') || 5060,
        sip_user     => $self->param('sip_user') // '',
        sip_password => $self->param('sip_password') // '',
    };
}

sub _generate_default_attributes ($self, $device) {
    my $generator = $DEFAULT_ATTRIBUTES{ $device->{vendor} } or return;
    my %attrs = $generator->($device);

    for my $key (keys %attrs) {
        $self->mysql->db->query(
            'INSERT INTO device_attributes (mac, attr_key, attr_value)
                 VALUES (?, ?, ?)
             ON DUPLICATE KEY UPDATE attr_value = VALUES(attr_value)',
            $device->{mac}, $key, $attrs{$key}
        );
    }
}

sub _find_or_404 ($self, $mac) {
    my $device = $self->mysql->db->query(
        'SELECT * FROM devices WHERE mac = ?', $mac
    )->hash;

    unless ($device) {
        $self->render(text => "Unknown device\n", status => 404);
        return undef;
    }

    return $device;
}

sub _form_error ($self, $message, $fields, $action) {
    $fields->{vendor} //= '';

    return $self->render(
        template => 'admin/devices/form',
        layout   => 'admin',
        device   => $fields,
        vendors  => \@VENDORS,
        action   => $action,
        error    => $message,
        status   => 422,
    );
}

1;
