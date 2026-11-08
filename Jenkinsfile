// Jenkinsfile — PROD/DR MCP pipeline demo
//
//   Jenkins (.105) → build Red Hat's linux-mcp-server → Aqua scan → Trivy
//   → build the Lunch Rolltable app → Aqua scan → Trivy
//   → export both artifacts → Ansible deploy to .105 (PROD) and .104 (DR)
//   → verify → failover drill → failback
//
// One pipeline builds and scans TWO images, Ansible deploys those exact
// artifacts to BOTH sites, and the MCP answers from whichever site is live.
//
//   artifact A: rhel-mcp         the INSPECTOR — the only privileged
//                               component. It SSHes into the host it runs on
//                               and reports what it sees.
//   artifact B: lunch-rolltable  the WORKLOAD — the page a user actually
//                               looks at. Its panel asks the MCP which site
//                               it is talking to, so the failover has a
//                               user-visible consequence.
//
// The drill moves the page and the MCP together: a site whose page is up but
// whose MCP is down would show a broken panel, and a site whose MCP is up but
// whose page is down has nothing to show at all.
//
// ---------------------------------------------------------------------------
// One-time setup required BEFORE the first build
//
//   1. Bare git origin inside the Jenkins container, served to Jenkins over
//      the git protocol (no GitHub dependency, and the Jenkins container does
//      NOT need to be recreated):
//        podman exec jenkins mkdir -p /var/jenkins_home/git
//        podman exec jenkins git init --bare /var/jenkins_home/git/mcp-dr-pipeline.git
//        podman exec jenkins git daemon --detach --reuseaddr --listen=127.0.0.1 \
//            --port=9418 --base-path=/var/jenkins_home/git --export-all \
//            /var/jenkins_home/git
//      (scripts/install-jenkins-tools.sh does both, and is idempotent.)
//      Then push this repo into it (from the laptop):
//        git remote add jenkins-local file:///var/jenkins_home/git/mcp-dr-pipeline.git
//        git push jenkins-local main
//
//   2. The agent must be able to run ansible + python3. The jenkins-with-podman
//      image ships neither:
//        podman cp scripts/install-jenkins-tools.sh jenkins:/var/jenkins_home/
//        podman exec jenkins bash /var/jenkins_home/install-jenkins-tools.sh
//      (This is lost if the container is recreated — re-run it.)
//
//   3. SSH key for the pipeline. The Ansible controller authenticates to each
//      site as that site's own deploy user (rhai on PROD, dr on DR) with the
//      key id_rhai108_rsa. The private key must live in the Jenkins container:
//        podman exec jenkins mkdir -p /var/jenkins_home/.ssh
//        podman cp ~/.ssh/id_rhai108_rsa jenkins:/var/jenkins_home/.ssh/
//        podman exec jenkins chmod 600 /var/jenkins_home/.ssh/id_rhai108_rsa
//      and the matching PUBLIC key must be in BOTH sites' authorized_keys.
//      .105 already trusts it. .104 needs it — see RUNBOOK.md.
//
//   4. DR site one-time root setup (firewall + linger) — see RUNBOOK.md.
//      Without it the DR endpoint cannot be reached from the network and the
//      systemd USER unit dies at logout.
//
//   5. Credential "aqua-console" (same as the HKU intranet job):
//        Manage Jenkins → Credentials → (global) → Add Credentials
//        Kind: Username with password | ID: aqua-console | Username: administrator
//
//   6. Pipeline job configuration
//        Definition:  Pipeline script from SCM
//        SCM:         Git | git://127.0.0.1:9418/mcp-dr-pipeline.git
//        Branch:      */main
//        Script Path: Jenkinsfile
//
//   7. The Aqua console container on the host must have a working OUTBOUND
//      path (cybercenter5.aquasec.com). Symptom + fix are documented in the
//      HKU intranet Jenkinsfile — `podman network reload` on the host.
//
// ---------------------------------------------------------------------------
// What gets built
//
//   The MCP server is Red Hat's official linux-mcp-server, UNMODIFIED. The
//   upstream Containerfile is used as-is from a pinned commit:
//       6d7ca1d1da8598c2e816fd69e98b8f7cf97da0d1  (27 commits past tag 1.5.0)
//   The pinned commit is fetched from GitHub at build time; nothing is
//   vendored into this repository.
//
//   The upstream image sets `ENV container=docker`, which makes the MCP
//   REFUSE to execute locally and require a remote `host` over SSH. That is
//   deliberate and it is what makes the PROD/DR demo work: the container
//   runs with --network host and inspects ITS OWN host's sshd, so the answer
//   identifies the site that is actually serving.
//
// ---------------------------------------------------------------------------
// Image version tags
//
//       v<major>.<minor>.<DDMMYY><NN>       e.g. v1.0.29102601
//
//   major.minor  from the VERSION file in the repo root.
//   DDMMYY       build date, pinned to Hong Kong time.
//   NN           Jenkins build number, zero padded.
//
// ---------------------------------------------------------------------------
// The artifact travels as a tarball, not through the registry
//
//   The DR site must be able to receive a promoted image even when the PROD
//   registry is down — that is the whole point of a DR site. So the pipeline
//   exports `podman save | gzip` and Ansible copies that ONE file to both
//   sites, which load it into their own rootless podman store. Both sites
//   therefore run byte-identical content.
// ===========================================================================

pipeline {
    agent any

    environment {
        AQUA_HOST     = 'https://192.168.147.105'
        SCANNER_IMAGE = 'registry.aquasec.com/scanner:2022.4.868'
        TRIVY_IMAGE   = 'docker.io/aquasec/trivy:0.76.1'
        AQUA_CREDS_ID = 'aqua-console'

        IMAGE_NAME    = 'rhel-mcp'

        // The upstream MCP source, pinned to the exact commit validated in
        // this repository (27 commits past tag 1.5.0).
        MCP_REPO      = 'rhel-lightspeed/linux-mcp-server'
        MCP_COMMIT    = '6d7ca1d1da8598c2e816fd69e98b8f7cf97da0d1'

        // The second artifact: the Lunch Rolltable app, the user-facing
        // workload that moves between the two sites. Pinned to the exact
        // commit, fetched from GitHub at build time — nothing is vendored.
        APP_REPO       = 'MangoTim/aqua-rolltable-demo'
        APP_COMMIT     = '2e745904cb7f21e18cbf9b2a1881168a0ff5ed3b'
        APP_IMAGE_NAME = 'lunch-rolltable'

        // The two sites of the demo.
        PROD_HOST     = '192.168.147.105'
        DR_HOST       = '192.168.147.104'
        MCP_PORT      = '8095'
        MCP_PATH      = '/mcp'
        APP_PORT      = '8084'

        // The hostname each site reports when the MCP inspects it. These are
        // the PROOF of which site is serving: same image, different answer.
        PROD_EXPECT   = 'server-gateway.example.com'
        DR_EXPECT     = 'localhost.localdomain'

        // The DR readiness gate. Before the drill promotes the standby, the
        // MCP asks it what it can see of its own host and the answer is
        // checked against these minimums. A standby that cannot hold the
        // load is never promoted — the drill rolls back and the build fails.
        DR_MIN_CPU_CORES         = '2'
        DR_MIN_FREE_MEM_PERCENT  = '10'
        DR_MIN_FREE_DISK_PERCENT = '10'

        // GIT_ORIGIN is the bare repo inside the Jenkins container, served by
        // the local git daemon (see scripts/install-jenkins-tools.sh). It is
        // git:// and NOT file:// on purpose: the git plugin refuses to check
        // out a local directory unless the JVM was started with
        // -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true, and that flag
        // is a static final read once at class load, so it cannot be enabled
        // at runtime. A git:// url is an ordinary remote and just works.
        GIT_ORIGIN    = 'git://127.0.0.1:9418/mcp-dr-pipeline.git'
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 40, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    parameters {
        // Run the PROD/DR drill as part of this build?
        //
        // The drill is a REAL state change: PROD goes down, the standby takes
        // over, and PROD comes back. That is what makes a green build the
        // proof of the whole story — but it is also the reason the drill
        // exists as its own jobs (mcp-failover / mcp-failback): a CI build
        // should never take production down, and failover and failback are
        // two decisions made at two different times.
        //
        // Leave this ON for the demo. Turn it OFF for a routine build.
        booleanParam(
            name: 'RUN_DRILL',
            defaultValue: true,
            description: 'Run the PROD/DR failover drill and failback in this build')
    }

    stages {

        stage('Checkout') {
            steps {
                git branch: 'main', url: env.GIT_ORIGIN
            }
        }

        stage('Fetch MCP Source') {
            // The upstream source is downloaded from GitHub at build time and
            // pinned to an exact commit. Nothing is vendored in this repo, so
            // there is no second copy of Red Hat's code to keep in sync.
            steps {
                sh '''
                    set -eux
                    rm -rf upstream mcp-src.tar.gz
                    curl -fsSL --retry 3 --retry-delay 5 \
                        -o mcp-src.tar.gz \
                        "https://github.com/${MCP_REPO}/archive/${MCP_COMMIT}.tar.gz"
                    mkdir -p upstream
                    tar -xzf mcp-src.tar.gz -C upstream --strip-components=1
                    test -f upstream/Containerfile
                    echo "upstream source ready:"
                    ls upstream | head -20
                '''
            }
        }

        stage('Fetch App Source') {
            // The app source is downloaded from GitHub at build time and pinned
            // to an exact commit, exactly like the MCP source. The app is the
            // pipeline's second artifact, so it follows the same rules: nothing
            // is vendored, and what ships is the commit that was scanned.
            steps {
                sh '''
                    set -eux
                    rm -rf app-src app-src.tar.gz
                    curl -fsSL --retry 3 --retry-delay 5 \
                        -o app-src.tar.gz \
                        "https://github.com/${APP_REPO}/archive/${APP_COMMIT}.tar.gz"
                    mkdir -p app-src
                    tar -xzf app-src.tar.gz -C app-src --strip-components=1
                    test -f app-src/Dockerfile
                    test -f app-src/serve.py
                    test -f app-src/mcp_client.py
                    echo "app source ready:"
                    ls app-src
                '''
            }
        }

        stage('Resolve Version') {
            steps {
                script {
                    def base = sh(script: "tr -d ' \\n' < VERSION", returnStdout: true).trim()
                    def day  = sh(script: "TZ=Asia/Hong_Kong date +%d%m%y", returnStdout: true).trim()
                    def seq  = sh(script: "printf '%02d' ${BUILD_NUMBER}", returnStdout: true).trim()

                    env.IMAGE_VERSION = "v${base}.${day}${seq}"
                    env.FULL_IMAGE    = "${env.IMAGE_NAME}:${env.IMAGE_VERSION}"
                    env.BASE_IMAGE    = "${env.IMAGE_NAME}:${env.IMAGE_VERSION}"
                    env.ARTIFACT      = "${env.IMAGE_NAME}-${env.IMAGE_VERSION}.tar.gz"

                    // The app ships as the same release — one build, two
                    // artifacts, one version.
                    env.APP_FULL_IMAGE = "${env.APP_IMAGE_NAME}:${env.IMAGE_VERSION}"
                    env.APP_ARTIFACT   = "${env.APP_IMAGE_NAME}-${env.IMAGE_VERSION}.tar.gz"

                    echo "Image version : ${env.IMAGE_VERSION}"
                    echo "Full image ref: ${env.FULL_IMAGE}"
                    echo "Artifact      : ${env.ARTIFACT}"
                    echo "App image ref : ${env.APP_FULL_IMAGE}"
                    echo "App artifact  : ${env.APP_ARTIFACT}"
                }
            }
        }

        stage('Build Image') {
            // --network host : the build needs to reach the UBI registry and
            //                  PyPI. The host's rootful podman bridge is
            //                  firewalled (container egress is dropped in
            //                  the FORWARD chain), so a default bridge build
            //                  hangs on the pip install. Host networking
            //                  routes build egress through OUTPUT instead.
            // --format docker: podman's default OCI format silently DROPS
            //                  the HEALTHCHECK instruction; docker format
            //                  keeps it and is what the scanners expect.
            steps {
                sh '''
                    set -eux
                    podman build \
                        --file upstream/Containerfile \
                        --format docker \
                        --network host \
                        --tag ${FULL_IMAGE} \
                        --label build.number=${BUILD_NUMBER} \
                        --label build.url=${BUILD_URL} \
                        upstream

                    podman image inspect ${FULL_IMAGE} --format 'id={{.Id}} size={{.Size}}'
                '''
            }
        }

        stage('Build App Image') {
            // The same two flags as the MCP build:
            //   --network host  the build has to reach the Debian registry and
            //                   the apt mirrors. The host's firewalld FORWARD
            //                   chain drops container egress, so a default
            //                   bridge build hangs.
            //   --format docker  what the scanners expect.
            steps {
                sh '''
                    set -eux
                    podman build \
                        --file app-src/Dockerfile \
                        --format docker \
                        --network host \
                        --tag ${APP_FULL_IMAGE} \
                        --label build.number=${BUILD_NUMBER} \
                        --label build.url=${BUILD_URL} \
                        app-src

                    podman image inspect ${APP_FULL_IMAGE} --format 'id={{.Id}} size={{.Size}}'
                '''
            }
        }

        stage('Aqua Image Scan') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: "${AQUA_CREDS_ID}",
                    usernameVariable: 'AQUA_USER',
                    passwordVariable: 'AQUA_PASSWORD'
                )]) {
                    sh '''
                        set -u

                        # Capture the scanner exit code instead of letting
                        # `set -e` kill the shell — otherwise a scanner failure
                        # produces no diagnostic at all, only a red stage.
                        SCAN_RC=0
                        podman run --rm --name aqua-scan-${BUILD_NUMBER} \
                            --network host \
                            --security-opt label=disable --user root \
                            -v /var/run/docker.sock:/var/run/docker.sock \
                            ${SCANNER_IMAGE} \
                            scan \
                                --host ${AQUA_HOST} \
                                --local ${FULL_IMAGE} \
                                --no-verify \
                                --user ${AQUA_USER} \
                                --password ${AQUA_PASSWORD} \
                                --html > aqua-report.html 2> aqua-scan.err || SCAN_RC=$?

                        if [ "${SCAN_RC}" -ne 0 ]; then
                            echo "--- Aqua scanner stderr ---"
                            cat aqua-scan.err || true
                            echo "--- Aqua scanner output ---"
                            cat aqua-report.html || true
                            echo ""
                            echo "BLOCKED: Aqua scanner CLI exited ${SCAN_RC}"
                            echo "HINT: 'TLS handshake timeout' / 'Failed checking cybercenter to"
                            echo "      scanner compatibility' means the aqua-web console container"
                            echo "      on the Jenkins host has lost its outbound path. Fix on the"
                            echo "      host with:  podman network reload"
                            exit 1
                        fi

                        echo "--- Aqua scan summary ---"
                        grep -oE "Image Is (Compliant|Non-compliant)" aqua-report.html || true
                        # Hard CI/CD gate: the pipeline only proceeds if the
                        # image is Compliant.
                        grep -q "Image Is Compliant" aqua-report.html \
                            || { echo "BLOCKED: image is non-compliant (or scan report missing compliance marker)"; exit 1; }
                    '''
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'aqua-report.html,aqua-scan.err',
                                     allowEmptyArchive: true
                }
            }
        }

        stage('Aqua Image Scan (App)') {
            // The same gate, the same console, the same policy — on the app
            // image. Only the container name and the report file differ, so
            // both artifacts' reports are archived side by side.
            steps {
                withCredentials([usernamePassword(
                    credentialsId: "${AQUA_CREDS_ID}",
                    usernameVariable: 'AQUA_USER',
                    passwordVariable: 'AQUA_PASSWORD'
                )]) {
                    sh '''
                        set -u

                        SCAN_RC=0
                        podman run --rm --name aqua-scan-app-${BUILD_NUMBER} \
                            --network host \
                            --security-opt label=disable --user root \
                            -v /var/run/docker.sock:/var/run/docker.sock \
                            ${SCANNER_IMAGE} \
                            scan \
                                --host ${AQUA_HOST} \
                                --local ${APP_FULL_IMAGE} \
                                --no-verify \
                                --user ${AQUA_USER} \
                                --password ${AQUA_PASSWORD} \
                                --html > aqua-report-app.html 2> aqua-scan-app.err || SCAN_RC=$?

                        if [ "${SCAN_RC}" -ne 0 ]; then
                            echo "--- Aqua scanner stderr ---"
                            cat aqua-scan-app.err || true
                            echo "--- Aqua scanner output ---"
                            cat aqua-report-app.html || true
                            echo ""
                            echo "BLOCKED: Aqua scanner CLI exited ${SCAN_RC}"
                            exit 1
                        fi

                        echo "--- Aqua scan summary (app) ---"
                        grep -oE "Image Is (Compliant|Non-compliant)" aqua-report-app.html || true
                        # Hard CI/CD gate: the pipeline only proceeds if image is Compliant.
                        grep -q "Image Is Compliant" aqua-report-app.html \
                            || { echo "BLOCKED: the app image is non-compliant (or scan report missing compliance marker)"; exit 1; }
                    '''
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'aqua-report-app.html,aqua-scan-app.err',
                                     allowEmptyArchive: true
                }
            }
        }

        stage('Trivy Scan') {
            // The BASELINE scan. It produces the finding list that the
            // Security Remediation stage acts on, and it hard-gates the OS
            // packages of the shipped base image.
            //
            // The library findings are NOT gated here: they are gated after
            // remediation, by the "Trivy Final Scan" stage, on the image that
            // is actually exported and deployed to both sites.
            steps {
                sh '''
                    set -u

                    # ------------------------------------------------------------------
                    # 1. Library CVEs — the Python dependency tree of the MCP server
                    #    (fastmcp, uvicorn, starlette, asyncssh, ...).
                    #
                    #    JSON is the machine readable form the remediation stage
                    #    parses; the table below is the human readable form that
                    #    is archived as the build evidence.
                    # ------------------------------------------------------------------
                    TRIVY_RC=0
                    podman run --rm --name mcp-trivy-${BUILD_NUMBER} \
                        --network host --security-opt label=disable \
                        -v /var/run/docker.sock:/var/run/docker.sock \
                        -v trivy-cache:/root/.cache/trivy \
                        -e TRIVY_DB_REPOSITORY=docker.io/aquasec/trivy-db:2 \
                        ${TRIVY_IMAGE} \
                        image --scanners vuln \
                            --pkg-types library \
                            --severity HIGH,CRITICAL \
                            --exit-code 1 \
                            --format json \
                            ${FULL_IMAGE} > trivy-report.json 2> trivy-scan.err || TRIVY_RC=$?

                    python3 - <<'PY' > trivy-report.txt
import json

with open("trivy-report.json", encoding="utf-8") as fh:
    report = json.load(fh)

for result in report.get("Results") or []:
    findings = result.get("Vulnerabilities") or []
    print("Target: %s (%s)" % (result.get("Target"), result.get("Class")))
    if not findings:
        print("    no HIGH/CRITICAL findings")
    for vuln in findings:
        print("    %-24s %-14s %-9s -> %s" % (
            vuln.get("PkgName"),
            vuln.get("InstalledVersion"),
            vuln.get("Severity"),
            vuln.get("FixedVersion") or "NO FIX PUBLISHED",
        ))
    print("")
PY

                    cat trivy-report.txt
                    echo "trivy (library) exit code: ${TRIVY_RC}"

                    # ------------------------------------------------------------------
                    # 2. OS packages of the shipped base (UBI 10 minimal).
                    #    CRITICAL is the gate.
                    # ------------------------------------------------------------------
                    TRIVY_OS_RC=0
                    podman run --rm --name mcp-trivy-os-${BUILD_NUMBER} \
                        --network host --security-opt label=disable \
                        -v /var/run/docker.sock:/var/run/docker.sock \
                        -v trivy-cache:/root/.cache/trivy \
                        -e TRIVY_DB_REPOSITORY=docker.io/aquasec/trivy-db:2 \
                        ${TRIVY_IMAGE} \
                        image --scanners vuln \
                            --pkg-types os \
                            --severity CRITICAL \
                            --exit-code 1 \
                            --format table \
                            ${FULL_IMAGE} > trivy-os-report.txt 2>&1 || TRIVY_OS_RC=$?

                    cat trivy-os-report.txt
                    echo "trivy (OS packages) exit code: ${TRIVY_OS_RC}"

                    if [ "${TRIVY_OS_RC}" -ne 0 ]; then
                        echo "BLOCKED: Trivy reported a CRITICAL OS vulnerability in the MCP image — see trivy-os-report.txt"
                        exit 1
                    fi

                    echo "Baseline scan done. Library findings are remediated in the next stage."
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'trivy-report.txt,trivy-report.json,trivy-os-report.txt,trivy-scan.err',
                                     allowEmptyArchive: true
                }
            }
        }

        stage('Trivy Scan (App)') {
            // The app's gate. Two things make it simpler than the MCP's:
            //
            //   1. OS packages only. The app image has NO pip dependencies —
            //      it is the Python standard library and three source files.
            //      There is no library tree to report and, more importantly,
            //      NO remediation stage: there is nothing to upgrade.
            //   2. The base image carries an `apt-get upgrade` in its
            //      Dockerfile, so the Debian package set is already patched
            //      when the image is built. The gate proves it.
            //
            // CRITICAL is the gate, exactly like the MCP's OS gate.
            steps {
                sh '''
                    set -u

                    TRIVY_OS_RC=0
                    podman run --rm --name app-trivy-os-${BUILD_NUMBER} \
                        --network host --security-opt label=disable \
                        -v /var/run/docker.sock:/var/run/docker.sock \
                        -v trivy-cache:/root/.cache/trivy \
                        -e TRIVY_DB_REPOSITORY=docker.io/aquasec/trivy-db:2 \
                        ${TRIVY_IMAGE} \
                        image --scanners vuln \
                            --pkg-types os \
                            --severity CRITICAL \
                            --exit-code 1 \
                            --format table \
                            ${APP_FULL_IMAGE} > trivy-app-os-report.txt 2>&1 || TRIVY_OS_RC=$?

                    cat trivy-app-os-report.txt
                    echo "trivy (app, OS packages) exit code: ${TRIVY_OS_RC}"

                    if [ "${TRIVY_OS_RC}" -ne 0 ]; then
                        echo "BLOCKED: Trivy reported a CRITICAL OS vulnerability in the app image — see trivy-app-os-report.txt"
                        exit 1
                    fi

                    echo "App scan done: no CRITICAL OS CVEs, and there are no library dependencies to remediate."
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'trivy-app-os-report.txt',
                                     allowEmptyArchive: true
                }
            }
        }

        stage('Security Remediation') {
            // The upstream image is built from a pinned commit, so its Python
            // dependency tree is fixed — and that tree carries published
            // CVEs. They are fixed HERE, inside the image, and the result is
            // re-scanned with a hard gate. What ships is the remediated image.
            //
            // Two kinds of finding are handled:
            //
            //   1. The MCP's OWN dependencies — authlib, pyjwt, certifi,
            //      dnspython, joserfc. These are upgraded in place to the
            //      version Trivy names as the fix.
            //
            //   2. The copies that pip bundles inside its own _vendor
            //      directory — urllib3, msgpack, requests, ... They are real
            //      files in the image, but they are not importable by the MCP
            //      and there is no upstream fix to install. pip has no
            //      business in a runtime virtualenv, so it is removed, and
            //      its vendored copies go with it.
            //
            // The remediated image is a derived build: FROM the upstream
            // image, so every upstream layer, label, env var, user and
            // entrypoint is preserved exactly.
            steps {
                script {
                    env.REMEDIATED_IMAGE = "${env.IMAGE_NAME}-remediated:${env.IMAGE_VERSION}"
                }
                sh '''
                    set -u

                    # What is actually installed and importable in the image.
                    # Trivy also reports the packages pip keeps in its own
                    # _vendor directory; those are not in this list, so they
                    # are correctly left out of the upgrade list.
                    podman run --rm --name mcp-piplist-${BUILD_NUMBER} \
                        --pull=never --network host --security-opt label=disable \
                        --entrypoint /opt/venvs/mcp/bin/python \
                        ${FULL_IMAGE} \
                        -m pip list --format=freeze > pip-list.txt 2>/dev/null

                    # The upgrade list. Exit code 3 means a finding has no
                    # published fix — that cannot be remediated, so the build
                    # must stop rather than ship a knowingly vulnerable image.
                    FIX_RC=0
                    python3 scripts/trivy_cve_packages.py \
                        trivy-report.json \
                        --installed pip-list.txt \
                        > cve-fixes.txt || FIX_RC=$?

                    echo "--- packages to upgrade ---"
                    cat cve-fixes.txt

                    if [ "${FIX_RC}" -ne 0 ]; then
                        echo ""
                        if [ "${FIX_RC}" -eq 3 ]; then
                            echo "BLOCKED: Trivy found a HIGH/CRITICAL library CVE with no published fix."
                            echo "        It cannot be remediated automatically — the image must be"
                            echo "        rebuilt from a newer upstream commit."
                        else
                            echo "BLOCKED: could not build the remediation list (exit ${FIX_RC})."
                            echo "        See the error above and the archived trivy-report.json."
                        fi
                        exit 1
                    fi

                    # The upgrade command. Empty when Trivy found nothing to fix.
                    #
                    # NOTE: no backslashes in this block. Groovy processes
                    # escape sequences even inside a single-quoted string, so
                    # a doubled backslash here becomes a single one in the
                    # shell script and silently breaks it. The Containerfile
                    # is therefore written one line per echo.
                    FIXES=$(tr '\n' ' ' < cve-fixes.txt)
                    if [ -n "${FIXES}" ]; then
                        UPGRADE="/opt/venvs/mcp/bin/python -m pip install --no-cache-dir --no-deps --upgrade ${FIXES} ;"
                    else
                        UPGRADE="true ;"
                    fi

                    # The derived Containerfile: FROM the upstream image, so
                    # every upstream layer, label, env var, user and entrypoint
                    # is preserved exactly.
                    {
                        echo "FROM ${FULL_IMAGE}"
                        echo "USER root"
                        echo "RUN set -eux; ${UPGRADE} rm -rf /opt/venvs/mcp/lib/python3.12/site-packages/pip /opt/venvs/mcp/lib/python3.12/site-packages/pip-*.dist-info /opt/venvs/mcp/bin/pip* ; /opt/venvs/mcp/bin/python -c 'import fastmcp, linux_mcp_server, asyncssh'"
                        echo "USER mcp"
                    } > Containerfile.remediated

                    echo "--- derived Containerfile ---"
                    cat Containerfile.remediated

                    podman build --network host --pull=never --format docker \
                        --file Containerfile.remediated \
                        --tag ${REMEDIATED_IMAGE} \
                        .

                    podman image inspect ${REMEDIATED_IMAGE} --format 'id={{.Id}} size={{.Size}}'
                '''
                script {
                    // From here on, the remediated image IS the artifact. The
                    // export, deploy, verify and drill stages all refer to
                    // FULL_IMAGE, so re-pointing it here keeps the rest of
                    // the pipeline unchanged — and guarantees that what ships
                    // is the image that passed the final scan.
                    env.FULL_IMAGE = env.REMEDIATED_IMAGE
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'cve-fixes.txt,pip-list.txt,Containerfile.remediated',
                                     allowEmptyArchive: true
                }
            }
        }

        stage('Trivy Final Scan') {
            // The hard gate, on the image that is about to be exported and
            // deployed to both sites. This is the scan that has to be clean.
            steps {
                sh '''
                    set -u

                    TRIVY_RC=0
                    podman run --rm --name mcp-trivy-final-${BUILD_NUMBER} \
                        --network host --security-opt label=disable \
                        -v /var/run/docker.sock:/var/run/docker.sock \
                        -v trivy-cache:/root/.cache/trivy \
                        -e TRIVY_DB_REPOSITORY=docker.io/aquasec/trivy-db:2 \
                        ${TRIVY_IMAGE} \
                        image --scanners vuln \
                            --pkg-types library \
                            --severity HIGH,CRITICAL \
                            --exit-code 1 \
                            --format table \
                            ${REMEDIATED_IMAGE} > trivy-final-report.txt 2>&1 || TRIVY_RC=$?

                    cat trivy-final-report.txt
                    echo "trivy (final, library) exit code: ${TRIVY_RC}"

                    TRIVY_OS_RC=0
                    podman run --rm --name mcp-trivy-final-os-${BUILD_NUMBER} \
                        --network host --security-opt label=disable \
                        -v /var/run/docker.sock:/var/run/docker.sock \
                        -v trivy-cache:/root/.cache/trivy \
                        -e TRIVY_DB_REPOSITORY=docker.io/aquasec/trivy-db:2 \
                        ${TRIVY_IMAGE} \
                        image --scanners vuln \
                            --pkg-types os \
                            --severity CRITICAL \
                            --exit-code 1 \
                            --format table \
                            ${REMEDIATED_IMAGE} > trivy-final-os-report.txt 2>&1 || TRIVY_OS_RC=$?

                    cat trivy-final-os-report.txt
                    echo "trivy (final, OS) exit code: ${TRIVY_OS_RC}"

                    if [ "${TRIVY_RC}" -ne 0 ]; then
                        echo "BLOCKED: the remediated image still has a HIGH/CRITICAL library CVE — see trivy-final-report.txt"
                        exit 1
                    fi

                    if [ "${TRIVY_OS_RC}" -ne 0 ]; then
                        echo "BLOCKED: the remediated image has a CRITICAL OS vulnerability — see trivy-final-os-report.txt"
                        exit 1
                    fi

                    echo "Trivy OK on the shipped image: no HIGH/CRITICAL library CVEs, no CRITICAL OS CVEs."
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'trivy-final-report.txt,trivy-final-os-report.txt',
                                     allowEmptyArchive: true
                }
            }
        }

        stage('Export Artifact') {
            // The artifacts travel as tarballs so the DR site never depends
            // on the PROD registry. Both sites load these exact files.
            //
            // TWO artifacts, ONE version: the inspector and the workload that
            // is moved by the drill travel together, so a release is always
            // the pair.
            steps {
                sh '''
                    set -eux
                    podman save ${FULL_IMAGE}     | gzip > ${ARTIFACT}
                    podman save ${APP_FULL_IMAGE} | gzip > ${APP_ARTIFACT}
                    sha256sum ${ARTIFACT} ${APP_ARTIFACT} | tee ${ARTIFACT}.sha256
                    ls -lh ${ARTIFACT} ${APP_ARTIFACT}
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: "${env.ARTIFACT},${env.ARTIFACT}.sha256,${env.APP_ARTIFACT}",
                                     allowEmptyArchive: true
                }
            }
        }

        stage('Ansible Deploy') {
            // The SAME tarballs are copied to .105 and .104. Each site loads
            // them into its own rootless podman store and runs them as systemd
            // USER units — no root, no sudo password, no shared filesystem.
            //
            // Two artifacts, two roles: `mcp` and `rolltable`. site.yml plays
            // both roles on both sites, so the MCP and the app it serves are
            // deployed from the same release.
            steps {
                sh '''
                    set -eux
                    # The controller's SSH key. Set it explicitly: the
                    # container's HOME is /home/server, not JENKINS_HOME, so
                    # the "~" in ansible.cfg would not resolve to the key.
                    export ANSIBLE_PRIVATE_KEY_FILE="${JENKINS_HOME}/.ssh/id_rhai108_rsa"
                    test -r "${ANSIBLE_PRIVATE_KEY_FILE}"
                    cd ansible
                    ansible-playbook \
                        -i inventory.ini \
                        site.yml \
                        -e mcp_image=${FULL_IMAGE} \
                        -e mcp_artifact=${WORKSPACE}/${ARTIFACT} \
                        -e rolltable_image=${APP_FULL_IMAGE} \
                        -e rolltable_artifact=${WORKSPACE}/${APP_ARTIFACT}
                '''
            }
        }

        stage('Verify PROD') {
            // The verify client runs INSIDE the image that was just built, so
            // it tests the exact artifact that was shipped — and it needs no
            // extra dependency on the CI agent, because the image already
            // contains fastmcp.
            //
            // The script is piped into the container on STDIN and read by
            // `python -`. It is NOT bind-mounted: the podman DAEMON runs on
            // the host and cannot see the Jenkins container's workspace, so a
            // bind mount of a workspace path would fail.
            steps {
                sh '''
                    set -u
                    set -o pipefail
                    echo "===== PROD verification =====" | tee failover-transcript.txt
                    VERIFY_RC=0
                    podman run -i --rm --name mcp-verify-${BUILD_NUMBER} \
                        --pull=never --network host --security-opt label=disable \
                        --entrypoint /opt/venvs/mcp/bin/python \
                        ${FULL_IMAGE} \
                        - --url http://${PROD_HOST}:${MCP_PORT}${MCP_PATH} \
                           --target ${PROD_HOST} \
                           --expect ${PROD_EXPECT} \
                           --call get_listening_ports \
                           --assert get_listening_ports=${MCP_PORT} \
                        < scripts/mcp_verify.py 2>&1 | tee -a failover-transcript.txt || VERIFY_RC=$?

                    if [ "${VERIFY_RC}" -ne 0 ]; then
                        echo "BLOCKED: the PROD endpoint did not answer as ${PROD_EXPECT}"
                        exit 1
                    fi
                    echo "" | tee -a failover-transcript.txt

                    # ---- the app, end to end --------------------------------
                    # The page asks its OWN MCP which site it is talking to,
                    # and the MCP answers with the hostname of the host that
                    # is serving the page. So this is the full chain:
                    #     page -> MCP -> host
                    # If the page reports the PROD hostname, the same app
                    # image is serving on the PROD site. The script runs
                    # INSIDE the app image, so it tests the shipped artifact.
                    APP_VERIFY_RC=0
                    podman run -i --rm --name app-verify-${BUILD_NUMBER} \
                        --pull=never --network host --security-opt label=disable \
                        --entrypoint python \
                        ${APP_FULL_IMAGE} \
                        - --url http://${PROD_HOST}:${APP_PORT}/api/mcp/status \
                           --expect ${PROD_EXPECT} \
                           --role PROD \
                           --peer DR \
                        < scripts/app_verify.py 2>&1 | tee -a failover-transcript.txt || APP_VERIFY_RC=$?

                    if [ "${APP_VERIFY_RC}" -ne 0 ]; then
                        echo "BLOCKED: the app on PROD did not report ${PROD_EXPECT}"
                        exit 1
                    fi
                    echo "" | tee -a failover-transcript.txt
                '''
            }
        }

        stage('Failover Drill') {
            // Warm the DR standby, PROVE it can take the load, and only then
            // stand PROD down and promote DR. The SAME image is now serving,
            // but the answer identifies the DR host.
            //
            // If the readiness probe says DR is not fit, the drill rolls back
            // to the PROD-only posture and the BUILD FAILS — production was
            // never taken down.
            //
            // `!= false` and not a plain truth test: a build that runs
            // before the job has ever seen the parameter must still do the
            // drill. Only an explicit "off" skips it.
            when {
                expression { params.RUN_DRILL != false }
            }
            steps {
                sh '''
                    set -eu
                    set -o pipefail
                    export ANSIBLE_PRIVATE_KEY_FILE="${JENKINS_HOME}/.ssh/id_rhai108_rsa"

                    # 1. warm the standby, WITHOUT touching production
                    cd ansible
                    ansible-playbook -i inventory.ini dr-warmup.yml
                    cd ..

                    # 2. the readiness gate
                    echo "===== DR READINESS PROBE (before any cutover) =====" | tee -a failover-transcript.txt
                    PROBE_RC=0
                    podman run -i --rm --name mcp-probe-dr-${BUILD_NUMBER} \
                        --pull=never --network host --security-opt label=disable \
                        --entrypoint /opt/venvs/mcp/bin/python \
                        ${FULL_IMAGE} \
                        - --url http://${DR_HOST}:${MCP_PORT}${MCP_PATH} \
                           --target ${DR_HOST} \
                           --expect ${DR_EXPECT} \
                           --min-cpu-cores ${DR_MIN_CPU_CORES} \
                           --min-free-mem-percent ${DR_MIN_FREE_MEM_PERCENT} \
                           --min-free-disk-percent ${DR_MIN_FREE_DISK_PERCENT} \
                        < scripts/mcp_dr_probe.py 2>&1 | tee -a failover-transcript.txt || PROBE_RC=$?

                    if [ "${PROBE_RC}" -ne 0 ]; then
                        echo "BLOCKED: the DR site is not fit to take over. Rolling back."
                        cd ansible
                        ansible-playbook -i inventory.ini failback.yml || true
                        exit 1
                    fi
                    echo "" | tee -a failover-transcript.txt

                    # 3. the actual cutover
                    cd ansible
                    ansible-playbook -i inventory.ini failover.yml

                    cd ..
                    echo "===== FAILOVER: DR is now serving =====" | tee -a failover-transcript.txt
                    VERIFY_RC=0
                    podman run -i --rm --name mcp-verify-dr-${BUILD_NUMBER} \
                        --pull=never --network host --security-opt label=disable \
                        --entrypoint /opt/venvs/mcp/bin/python \
                        ${FULL_IMAGE} \
                        - --url http://${DR_HOST}:${MCP_PORT}${MCP_PATH} \
                           --target ${DR_HOST} \
                           --expect ${DR_EXPECT} \
                           --call get_listening_ports \
                           --assert get_listening_ports=${MCP_PORT} \
                        < scripts/mcp_verify.py 2>&1 | tee -a failover-transcript.txt || VERIFY_RC=$?

                    if [ "${VERIFY_RC}" -ne 0 ]; then
                        echo "BLOCKED: after failover the DR endpoint did not answer as ${DR_EXPECT}"
                        exit 1
                    fi
                    echo "" | tee -a failover-transcript.txt

                    # The page must be serving from DR now, and it must say so.
                    # The PROD tile on the page turns into "connection refused"
                    # — that is the peer tile reporting the site that went away.
                    APP_VERIFY_RC=0
                    podman run -i --rm --name app-verify-dr-${BUILD_NUMBER} \
                        --pull=never --network host --security-opt label=disable \
                        --entrypoint python \
                        ${APP_FULL_IMAGE} \
                        - --url http://${DR_HOST}:${APP_PORT}/api/mcp/status \
                           --expect ${DR_EXPECT} \
                           --role DR \
                           --peer PROD \
                        < scripts/app_verify.py 2>&1 | tee -a failover-transcript.txt || APP_VERIFY_RC=$?

                    if [ "${APP_VERIFY_RC}" -ne 0 ]; then
                        echo "BLOCKED: after failover the app did not report ${DR_EXPECT} on the DR site"
                        exit 1
                    fi
                    echo "" | tee -a failover-transcript.txt
                '''
            }
        }

        stage('Failback') {
            // The exact inverse: stop DR, bring PROD back, and prove the
            // answer came from PROD again.
            when {
                expression { params.RUN_DRILL != false }
            }
            steps {
                sh '''
                    set -eu
                    set -o pipefail
                    export ANSIBLE_PRIVATE_KEY_FILE="${JENKINS_HOME}/.ssh/id_rhai108_rsa"
                    cd ansible
                    ansible-playbook -i inventory.ini failback.yml

                    cd ..
                    echo "===== FAILBACK: PROD is serving again =====" | tee -a failover-transcript.txt
                    VERIFY_RC=0
                    podman run -i --rm --name mcp-verify-back-${BUILD_NUMBER} \
                        --pull=never --network host --security-opt label=disable \
                        --entrypoint /opt/venvs/mcp/bin/python \
                        ${FULL_IMAGE} \
                        - --url http://${PROD_HOST}:${MCP_PORT}${MCP_PATH} \
                           --target ${PROD_HOST} \
                           --expect ${PROD_EXPECT} \
                           --call get_listening_ports \
                           --assert get_listening_ports=${MCP_PORT} \
                        < scripts/mcp_verify.py 2>&1 | tee -a failover-transcript.txt || VERIFY_RC=$?

                    if [ "${VERIFY_RC}" -ne 0 ]; then
                        echo "BLOCKED: after failback the PROD endpoint did not answer as ${PROD_EXPECT}"
                        exit 1
                    fi
                    echo "" | tee -a failover-transcript.txt

                    # The page is back on PROD, reporting the PROD hostname.
                    APP_VERIFY_RC=0
                    podman run -i --rm --name app-verify-back-${BUILD_NUMBER} \
                        --pull=never --network host --security-opt label=disable \
                        --entrypoint python \
                        ${APP_FULL_IMAGE} \
                        - --url http://${PROD_HOST}:${APP_PORT}/api/mcp/status \
                           --expect ${PROD_EXPECT} \
                           --role PROD \
                           --peer DR \
                        < scripts/app_verify.py 2>&1 | tee -a failover-transcript.txt || APP_VERIFY_RC=$?

                    if [ "${APP_VERIFY_RC}" -ne 0 ]; then
                        echo "BLOCKED: after failback the app did not report ${PROD_EXPECT} on the PROD site"
                        exit 1
                    fi
                    echo "" | tee -a failover-transcript.txt
                '''
            }
        }
    }

    post {
        always {
            sh '''
                # Remove the sidecar containers this build started. They all
                # run with --rm, but a FAILED run can leave one behind.
                # BUILD_NUMBER is always set, so this list needs no guard.
                podman rm -f aqua-scan-${BUILD_NUMBER} \
                             aqua-scan-app-${BUILD_NUMBER} \
                             mcp-trivy-${BUILD_NUMBER} \
                             mcp-trivy-os-${BUILD_NUMBER} \
                             mcp-trivy-final-${BUILD_NUMBER} \
                             mcp-trivy-final-os-${BUILD_NUMBER} \
                             app-trivy-os-${BUILD_NUMBER} \
                             mcp-piplist-${BUILD_NUMBER} \
                             mcp-verify-${BUILD_NUMBER} \
                             mcp-verify-dr-${BUILD_NUMBER} \
                             mcp-verify-back-${BUILD_NUMBER} \
                             app-verify-${BUILD_NUMBER} \
                             app-verify-dr-${BUILD_NUMBER} \
                             app-verify-back-${BUILD_NUMBER} 2>/dev/null || true

                # Deliberately NOT --force: if a container is still running
                # from ${FULL_IMAGE}, rmi correctly refuses and the image
                # stays. That is the safe outcome.
                #
                # BASE_IMAGE is the pre-remediation image. FULL_IMAGE was
                # re-pointed at REMEDIATED_IMAGE by the Security Remediation
                # stage, so without it the upstream build would be left behind
                # as a dangling <none> layer on the host.
                #
                # FULL_IMAGE is empty when 'Resolve Version' never ran, so
                # every image reference is guarded on its own.
                if [ -n "${FULL_IMAGE}" ]; then
                    podman rmi ${FULL_IMAGE} ${REMEDIATED_IMAGE} ${BASE_IMAGE} 2>/dev/null || true
                else
                    echo "MCP image references unresolved — skipping their cleanup"
                fi

                # The app image is independent of the MCP's remediation chain,
                # so it gets its own guard.
                if [ -n "${APP_FULL_IMAGE}" ]; then
                    podman rmi ${APP_FULL_IMAGE} 2>/dev/null || true
                else
                    echo "App image reference unresolved — skipping its cleanup"
                fi
            '''

            archiveArtifacts artifacts: 'failover-transcript.txt,ansible.log',
                             allowEmptyArchive: true
        }
        success {
            echo "Pipeline SUCCESS — ${env.FULL_IMAGE} + ${env.APP_FULL_IMAGE} deployed to PROD and DR; failover and failback verified."
            emailext (
                subject: "✅ Build #${BUILD_NUMBER} PASSED — ${env.FULL_IMAGE} + ${env.APP_FULL_IMAGE} (PROD/DR MCP)",
                body: """<h2>PROD/DR MCP Pipeline — Build #${BUILD_NUMBER} PASSED</h2>
                    <p><b>Artifact A — the inspector (MCP)</b><br>
                       Image: <code>${env.FULL_IMAGE}</code><br>
                       Artifact: <code>${env.ARTIFACT}</code></p>
                    <p><b>Artifact B — the workload (Lunch Rolltable app)</b><br>
                       Image: <code>${env.APP_FULL_IMAGE}</code><br>
                       Artifact: <code>${env.APP_ARTIFACT}</code></p>
                    <p>Aqua image scans: <b>Image Is Compliant</b> (both images)<br>
                       Trivy on the shipped MCP image: no HIGH/CRITICAL library CVEs, no CRITICAL OS CVEs<br>
                       Trivy on the shipped app image: no CRITICAL OS CVEs (the app has no library dependencies)<br>
                       Security remediation: the upstream Python dependencies were upgraded
                       to their fixed versions and pip was removed from the runtime venv</p>
                    <p>Deployed to: PROD <code>${env.PROD_HOST}</code> and DR <code>${env.DR_HOST}</code> — same artifacts, both sites</p>
                    <p>Failover drill: PROD stopped → DR answered as <code>${env.DR_EXPECT}</code>,
                       and the app on <code>${env.DR_HOST}:${env.APP_PORT}</code> reported <code>${env.DR_EXPECT}</code><br>
                       Failback: PROD restored → answered as <code>${env.PROD_EXPECT}</code>,
                       and the app on <code>${env.PROD_HOST}:${env.APP_PORT}</code> reported <code>${env.PROD_EXPECT}</code></p>
                    <p>Reports: <a href=\"${BUILD_URL}artifact/\">aqua-report.html, aqua-report-app.html, trivy-report.txt, trivy-final-report.txt, trivy-app-os-report.txt, cve-fixes.txt, failover-transcript.txt</a><br>
                       Console: <a href=\"${BUILD_URL}console\">build console</a><br>
                       Build: <a href=\"${BUILD_URL}\">#${BUILD_NUMBER}</a></p>
                """,
                mimeType: 'text/html',
                to: 'tim.wong@systex.com.hk'
            )
        }
        failure {
            echo "Pipeline FAILED — check the failing stage above for the blocking finding"
            emailext (
                subject: "❌ Build #${BUILD_NUMBER} FAILED — PROD/DR MCP",
                body: """<h2>PROD/DR MCP Pipeline — Build #${BUILD_NUMBER} FAILED</h2>
                    <p>MCP image: <code>${env.FULL_IMAGE ?: 'unresolved'}</code><br>
                       App image: <code>${env.APP_FULL_IMAGE ?: 'unresolved'}</code></p>
                    <p>Check the console for the failure stage.</p>
                    <p>Reports: <a href=\"${BUILD_URL}artifact/\">aqua-report.html, aqua-report-app.html, trivy-report.txt, trivy-os-report.txt, trivy-app-os-report.txt, failover-transcript.txt</a><br>
                       Console: <a href=\"${BUILD_URL}console\">build console</a><br>
                       Build: <a href=\"${BUILD_URL}\">#${BUILD_NUMBER}</a></p>
                """,
                mimeType: 'text/html',
                attachLog: true,
                to: 'tim.wong@systex.com.hk'
            )
        }
    }
}
