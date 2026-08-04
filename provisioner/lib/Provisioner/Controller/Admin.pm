package Provisioner::Controller::Admin;
use Mojo::Base 'Mojolicious::Controller', -signatures;

my @VENDORS = qw(yealink polycom);

my %VENDOR_TEMPLATE = (
    yealink => 'config/yealink',
    polycom => 'config/polycom',
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

    my $template = $VENDOR_TEMPLATE{ $device->{vendor} };

    my $rendered_config =
      $template
      ? $self->render_to_string(
          template => $template,
          format   => 'cfg',
          device   => $device,
        )
      : undef;

    return $self->render(
        template => 'admin/devices/show',
        format   => 'html',
        layout   => 'admin',
        device   => $device,
        requests => $requests,
        config   => $rendered_config,
    );
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
