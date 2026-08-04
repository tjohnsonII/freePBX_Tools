package Provisioner;

use Mojo::Base 'Mojolicious', -signatures;

use Mojo::mysql;
use Mojo::Util qw(sha1_sum steady_time);

sub startup ($self) {
    my $config = $self->plugin('NotYAMLConfig');

    $self->secrets([$self->_session_secret]);

    # Hypnotoad daemonizes and detaches from the terminal, so without an
    # explicit path the app logger has nowhere visible to write once it's
    # running as a service.
    $self->log->path($self->home->child('log', $self->mode . '.log'))
      unless $self->mode eq 'development';

    my $db_password = $ENV{PROVISIONER_DB_PASSWORD};

    unless (defined $db_password) {
        my $password_file = $self->home->child('.db_password');

        die "No database password: set PROVISIONER_DB_PASSWORD or create "
          . "@{[$password_file->to_string]}\n"
          unless -f $password_file;

        $db_password = $password_file->slurp =~ s/\s+\z//r;
    }

    my $db = $config->{db};

    my $dsn = Mojo::URL->new('mysql://')->userinfo("$db->{user}:$db_password")
      ->host($db->{host})->port($db->{port})->path("/$db->{database}");

    $self->helper(
        mysql => sub {
            state $mysql = Mojo::mysql->new($dsn);
        }
    );

    $self->mysql->migrations->from_file(
        $self->home->child('migrations', 'provisioner.sql')
    )->migrate;

    $self->helper(
        normalize_mac => sub ($c, $raw_mac) {
            my $mac = lc($raw_mac // '');
            $mac =~ s/[^0-9a-f]//g;

            return unless $mac =~ /\A[0-9a-f]{12}\z/;
            return $mac;
        }
    );

    $self->hook(
        before_dispatch => sub ($c) {
            my $method = $c->req->method;
            my $path   = $c->req->url->path->to_string;
            my $remote = $c->tx->remote_address // 'unknown';

            $c->app->log->info(
                "request method=$method path=$path remote=$remote"
            );
        }
    );

    my $r = $self->routes;

    $r->get('/')->to(
        cb => sub ($c) {
            $c->render(
                text =>
                  "Mojolicious Perl Provisioning Server\n"
                  . "Health check: /health\n"
            );
        }
    );

    $r->get('/health')->to(
        cb => sub ($c) {
            $c->render(
                json => {
                    status      => 'ok',
                    application => 'provisioner-lab',
                    framework   => 'Mojolicious',
                    perl        => "$^V",
                }
            );
        }
    );

    # Yealink directory:
    # /yealink/directory/001565abcdef.xml
    $r->get('/yealink/directory/#filename')
      ->to('provision#yealink_directory');

    # Primary boot config, shared by Yealink and Polycom:
    # /001565abcdef.cfg
    $r->get('/#filename')->to('provision#boot_config');
}

sub _session_secret ($self) {
    return $ENV{PROVISIONER_SECRET} if defined $ENV{PROVISIONER_SECRET};

    my $secret_file = $self->home->child('.session_secret');

    unless (-f $secret_file) {
        $secret_file->spurt(sha1_sum(rand() . steady_time() . $$));
        chmod 0600, $secret_file->to_string;
    }

    return $secret_file->slurp =~ s/\s+\z//r;
}

1;
