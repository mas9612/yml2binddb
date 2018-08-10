# -*- coding: utf-8 -*-

import argparse
import sys
import yaml


def main():
    source, output, dont_abbrev, forward, reverse = parse_args()
    definition = parse_yml(source)

    if output is not None:
        ohandler = open(output, 'w')
    else:
        ohandler = sys.stdout

    if forward:
        build_forward_db(ohandler, definition, dont_abbrev)
    elif reverse:
        build_reverse_db(ohandler, definition, dont_abbrev)
    else:
        pass

    if output is not None:
        ohandler.close()


def parse_args():
    """
    parse_args returns parsed values of command line arguments

    () -> (string, string, bool, bool, bool)

    Returned value:
    - 1st: Source YAML file path
    - 2nd: Output file name
    - 3rd: Whether use abbreviated representation.
           If this is True, don't use abbreviated form.
    - 4th: Generate forward lookup zone DB
    - 5th: Generate reverse lookup zone DB
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', metavar='OUTFILE',
                        help='Output file name (Default: stdout)')
    parser.add_argument('-l', action='store_true',
                        help='Do not use abbreviated representation')
    parser.add_argument('YAML', help='Source YAML file path')

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-f', action='store_true',
                       help='''Only generate forward lookup zone DB.
                       If both -f and -r are given, -f will be used.''')
    group.add_argument('-r', action='store_true',
                       help='''Only generate reverse lookup zone DB
                       If both -f and -r are given, -f will be used.''')
    args = parser.parse_args()

    return args.YAML, args.o, args.l, args.f, args.r


def parse_yml(path):
    # TODO: implement (this method is WIP)
    # TODO: refactoring
    try:
        with open(path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print('[ERROR] File Not Found: Please check file path.',
              file=sys.stderr)
        sys.exit(1)

    try:
        yml_obj = yaml.load(content)
    except yaml.YAMLError as err:
        print('[ERROR] YAML Parse error:', file=sys.stderr)
        print(err, file=sys.stderr)
        sys.exit(1)

    TOP_LEVEL_REQUIRED = [
        ('ttl', str),
        ('domainBase', str),
        ('networkBase', str),
        ('soa', dict),
        ('nameservers', list),
        ('hosts', list)
    ]
    for key in TOP_LEVEL_REQUIRED:
        if key[0] not in yml_obj:
            print('[ERROR] Required key "{}" Not Found'.format(key[0]))
            sys.exit(1)
        if not isinstance(yml_obj[key[0]], key[1]):
            print('[ERROR] Key "{}" must be {}'.format(key[0], key[1]))
            sys.exit(1)

    if not yml_obj['domainBase'].endswith('.'):
        print('[ERROR] domainBase must be FQDN, end with "."')
        sys.exit(1)

    SOA_REQUIRED = [
        ('mail', [str]),
        ('refresh', [int, str]),
        ('retry', [int, str]),
        ('expire', [int, str]),
        ('ttl', [int, str]),
    ]
    SOA_OPTIONAL = [
        ('serial', int),
    ]
    for key in SOA_REQUIRED:
        if key[0] not in yml_obj['soa']:
            print('[ERROR] Required key "soa.{}" Not Found'.format(key[0]))
            sys.exit(1)
        if not any([isinstance(yml_obj['soa'][key[0]], t) for t in key[1]]):
            print('[ERROR] Key "{}" must be one of {}'.format(key[0], key[1]))
            sys.exit(1)

    for key in SOA_OPTIONAL:
        if key[0] in yml_obj['soa'] and \
                not isinstance(yml_obj['soa'][key[0]], key[1]):
            print('[ERROR] Key "{}" must be {}'.format(key[0], key[1]))
            sys.exit(1)

    NS_REQUIRED = ['hostname']
    for i, ns in enumerate(yml_obj['nameservers']):
        for key in NS_REQUIRED:
            if key not in ns:
                print('[ERROR] Required key "nameservers[{}].{}" Not Found'
                      .format(i, key))

    HOST_REQUIRED = ['hostname', 'ip']
    for i, host in enumerate(yml_obj['hosts']):
        for key in HOST_REQUIRED:
            if key not in host:
                print('[ERROR] Required key "hosts[{}].{}" Not Found'
                      .format(i, key))

    return normalize(yml_obj)


def normalize(definition):
    mail = definition['soa']['mail']
    mail = mail.replace('@', '.') + '.'
    definition['soa']['mail'] = mail

    for ns in definition['nameservers']:
        if ns['hostname'].find('.') != -1:
            ns['hostname'] = ns['hostname'].split('.')[0]

    for host in definition['hosts']:
        if host['hostname'].find('.') != -1:
            host['hostname'] = host['hostname'].split('.')[0]

    return definition


def build_header(ohandler, definition, dont_abbrev):
    """
    build_header write generated SOA record to ohandler

    (file_handler, dict, bool) -> None
    """
    print('$TTL {}\n'.format(definition['ttl']), file=ohandler)

    # Build SOA record
    pri_dns = None
    for ns in definition['nameservers']:
        if 'master' in ns:
            pri_dns = ns['hostname']
            break
    if pri_dns is None:
        pri_dns = definition['nameservers'][0]['hostname']

    if dont_abbrev:
        domain_base = definition['domainBase']
    else:
        domain_base = '@'
    print('{} IN SOA {}.{} {} ('.format(
        domain_base, pri_dns, definition['domainBase'],
        definition['soa']['mail']
    ), file=ohandler)
    print('''    {}  ; refresh
    {}  ; retry
    {}  ; expire
    {}  ; ttl'''.format(
        definition['soa']['refresh'], definition['soa']['retry'],
        definition['soa']['expire'], definition['soa']['ttl']),
        file=ohandler
    )
    print(')\n', file=ohandler)


def build_forward_db(ohandler, definition, dont_abbrev):
    """
    build_forward_db write generated forward DB definition to ohandler

    (file_handler, dict, bool) -> None
    """
    build_header(ohandler, definition, dont_abbrev)

    # Build NS record
    for ns in definition['nameservers']:
        if dont_abbrev:
            hostname = '{}.{}'.format(ns['hostname'], definition['domainBase'])
        else:
            hostname = ns['hostname']

        print('    IN NS {}'.format(hostname), file=ohandler)
    print('', file=ohandler)

    # Build A/TXT record
    for host in definition['hosts']:
        if dont_abbrev:
            hostname = '{}.{}'.format(host['hostname'],
                                      definition['domainBase'])
        else:
            hostname = host['hostname']

        print('{}   IN A   {}'.format(hostname, host['ip']), file=ohandler)
        if 'description' in host:
            print('{}   IN TXT "{}"'.format(hostname, host['description'],
                                            file=ohandler))


def build_reverse_db(ohandler, definition, dont_abbrev):
    """
    build_reverse_db write generated reverse DB definition to ohandler

    (file_handler, dict, bool) -> None
    """
    build_header(ohandler, definition, dont_abbrev)

    # Build NS record
    for ns in definition['nameservers']:
        if dont_abbrev:
            hostname = '{}.{}'.format(ns['hostname'], definition['domainBase'])
        else:
            hostname = ns['hostname']

        print('    IN NS {}'.format(hostname), file=ohandler)
    print('', file=ohandler)

    # Build A/TXT record
    for host in definition['hosts']:
        if dont_abbrev:
            ip = host['ip']
        else:
            ip = host['ip'].split('.')[-1]

        fqdn = '{}.{}'.format(host['hostname'], definition['domainBase'])
        print('{}    IN PTR {}'.format(ip, fqdn), file=ohandler)
        if 'description' in host:
            print('{}    IN TXT "{}"'.format(ip, host['description']),
                  file=ohandler)


if __name__ == '__main__':
    main()
