package Provisioner::Controller::Provision;
use Mojo::Base 'Mojolicious::Controller', -signatures;

my %VENDOR_TEMPLATE = (
    yealink => 'config/yealink',
    polycom => 'config/polycom',
);

# Primary boot config, e.g. /001565abcdef.cfg
# Polycom per-phone override, chained from the master file above,
# e.g. /0004f2d49347-phone.cfg
sub boot_config ($self) {
    my $filename = $self->param('filename') // '';

    my $is_phone_override = $filename =~ /\A([0-9a-f]{12})-phone\.cfg\z/i;

    return $self->render(
        text   => "Invalid configuration filename\n",
        status => 400,
    ) unless $is_phone_override || $filename =~ /\A(.+)\.cfg\z/i;

    my $mac = $self->normalize_mac($1);

    return $self->render(
        text   => "Invalid MAC address\n",
        status => 400,
    ) unless $mac;

    my $device = $self->_find_device($mac);
    $self->_log_request($mac, $device);

    return $self->render(
        text   => "Unknown device\n",
        status => 404,
    ) unless $device;

    my $template =
      $is_phone_override
      ? 'config/polycom_phone'
      : $VENDOR_TEMPLATE{ $device->{vendor} };

    return $self->render(
        text   => "Unsupported vendor: $device->{vendor}\n",
        status => 501,
    ) unless $template;

    $self->res->headers->content_type('text/plain; charset=utf-8');
    $self->res->headers->cache_control(
        'no-store, no-cache, must-revalidate, max-age=0'
    );

    return $self->render(
        template => $template,
        format   => 'cfg',
        device   => $device,
    );
}

# Yealink phone-book directory, e.g. /yealink/directory/001565abcdef.xml
sub yealink_directory ($self) {
    my $filename = $self->param('filename') // '';

    return $self->render(
        text   => "Invalid directory filename\n",
        status => 400,
    ) unless $filename =~ /\A(.+)\.xml\z/i;

    my $mac = $self->normalize_mac($1);

    return $self->render(
        text   => "Invalid MAC address\n",
        status => 400,
    ) unless $mac;

    my $device = $self->_find_device($mac);
    $self->_log_request($mac, $device);

    return $self->render(
        text   => "Unknown directory\n",
        status => 404,
    ) unless $device && $device->{vendor} eq 'yealink';

    $self->res->headers->content_type('application/xml; charset=utf-8');
    $self->res->headers->cache_control('no-store');

    return $self->render(
        template => 'yealink/directory',
        format   => 'xml',
        device   => $device,
    );
}

# Devices PUT their own boot/app logs back to us, e.g.
# PUT /0004f2d49347-boot.log
sub upload_log ($self) {
    my $filename = $self->param('filename') // '';

    return $self->render(text => "Invalid filename\n", status => 400)
      unless $filename =~ /\A[a-f0-9]{12}-(boot|app)\.log\z/i;

    my $uploads_dir = $self->app->home->child('data', 'uploads');
    $uploads_dir->make_path;

    $uploads_dir->child($filename)->spurt($self->req->body);

    $self->app->log->info(
        "Received device log upload: $filename ("
          . length($self->req->body)
          . " bytes)"
    );

    return $self->render(text => '', status => 204);
}

sub _find_device ($self, $mac) {
    return $self->mysql->db->query(
        'SELECT * FROM devices WHERE mac = ?', $mac
    )->hash;
}

sub _log_request ($self, $mac, $device) {
    my $matched = $device ? 1 : 0;

    eval {
        $self->mysql->db->query(
            'INSERT INTO provisioning_requests
                 (mac, path, remote_addr, user_agent, matched)
             VALUES (?, ?, ?, ?, ?)',
            $mac,
            $self->req->url->path->to_string,
            $self->tx->remote_address,
            $self->req->headers->user_agent,
            $matched,
        );
        1;
    } or $self->app->log->error(
        "Failed to log provisioning request for $mac: $@"
    );
}

1;
