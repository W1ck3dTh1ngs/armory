#!/usr/bin/env python
from database.repositories import DomainRepository, BaseDomainRepository, IPRepository
from included.ModuleTemplate import ToolTemplate
from included.utilities import get_domain_ip
import io
import os
import pdb

class Module(ToolTemplate):
    name = "Subfinder"
    binary_name = "subfinder"

    def __init__(self, db):
        self.db = db
        self.BaseDomains = BaseDomainRepository(db, self.name)
        self.Domains = DomainRepository(db, self.name)
        self.IPs = IPRepository(db, self.name)

    def set_options(self):
        super(Module, self).set_options()
        self.options.add_argument(
            "-d", "--domain", help="Domain to run subfinder against."
        )
        self.options.add_argument(
            "-dL",
            "--domain_list",
            help="Read in a list of domains within the given file.",
        )
        self.options.add_argument(
            "-i",
            "--db_domains",
            help="Import the domains from the database.",
            action="store_true",
        )

        self.options.add_argument(
            "--rescan", help="Overwrite files without asking", action="store_true"
        )

    def get_targets(self, args):
        targets = []
        outpath = ""
        if args.output_path[0] == "/":
            output_path = os.path.join(
                self.base_config["PROJECT"]["base_path"], args.output_path[1:]
            )
        else:
            output_path = os.path.join(
                self.base_config["PROJECT"]["base_path"], args.output_path
            )
        if not os.path.exists(output_path):
            os.makedirs(output_path)
            
        if args.domain:
            out_file = os.path.join(outpath, "{}.subfinder".format(args.domain))
            targets.append({"target": args.domain, "output": os.path.join(output_path, out_file)})

        if args.db_domains:
            if args.rescan:
                domains = self.BaseDomains.all(scope_type="passive")
            else:
                domains = self.BaseDomains.all(tool=self.name, scope_type="passive")
            for d in domains:
                out_file = os.path.join(outpath, "{}.subfinder".format(d.domain))
                targets.append({"target": d.domain, "output": os.path.join(output_path, out_file)})
        

        elif args.domain_list:
            domains = io.open(args.domain_list, encoding="utf-8").read().split("\n")
            for d in domains:
                if d:
                    targets.append(
                        {
                            "target": d,
                            "output": os.path.join(
                                output_path, "{}.subfinder".format(d)
                            ),
                        }
                    )
        
        return targets

    def build_cmd(self, args):
        if args.binary:
            cmd = "{} ".format(args.binary)
        else:
            cmd = "{} ".format(self.binary_name)
        cmd = "{} -o {} -d {}".format(cmd, "{output}", "{target}")
        return cmd

    def process_output(self, targets):
        for target in targets:
            with io.open(target["output"], encoding="utf-8") as fd:
                for line in fd:
                    domain = line.strip()
                    ips = get_domain_ip.run(domain)
                    ip_obj = None
                    _, dom = self.Domains.find_or_create(domain=domain)
                    if ips:
                        for ip in ips:
                            _, ip_obj = self.IPs.find_or_create(ip_address=ip)
                            if ip_obj:
                                dom.ip_addresses.append(ip_obj)
                        dom.save()
        self.BaseDomains.commit()
        self.IPs.commit()

    def post_run(self, args):
        # Remove the temporary db file if it was created.
        if getattr(self, "db_domain_file", None):
            try:
                os.unlink(self.db_domain_file)
            except IOError as e:
                print("Failed to remove the Subfinder db temp file: '{}'.".format(e))

    def __get_tempfile(self, domain=None, args=None):
        # Create a temporary file and place all of the current database domains within the file.
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(delete=False) as fd:
            if domain:
                fd.write("{}\n".format(domain).encode("utf-8"))
            else:
                # Go through the database and grab the domains adding them to the file.
                if args.rescan:
                    domains = self.BaseDomains.all(passive_scope=True)
                else:
                    domains = self.BaseDomains.all(tool=self.name, passive_scope=True)
                if domains:
                    for domain in domains:
                        fd.write("{}\n".format(domain.domain).encode("utf-8"))
                else:
                    return None
        return fd.name