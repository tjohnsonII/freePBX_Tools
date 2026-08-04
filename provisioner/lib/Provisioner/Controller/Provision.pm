package Provisioner::Controller::Provision;
use Mojo::Base 'Mojolicious::Controller', -signatures;

my %VENDOR_TEMPLATE = (
    yealink => 'config/yealink',
    polycom => 'config/polycom',
);

# Primary boot config, e.g. /001565abcdef.cfg
sub boot_config ($self) {
    my $filename = $self->param('filename') // '';

    return $self->render(
        text   => "Invalid configuration filename\n",
        status => 400,
    ) unless $filename =~ /\A(.+)\.cfg\z/i;

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

    my $template = $VENDOR_TEMPLATE{ $device->{vendor} };

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
