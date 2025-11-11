# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from __future__ import annotations

import atr.blueprints.post as post
import atr.db as db
import atr.get as get
import atr.models.distribution as distribution
import atr.shared as shared
import atr.storage as storage
import atr.web as web


@post.committer("/distribution/delete/<project>/<version>")
@post.form(shared.distribution.DeleteForm)
async def delete(
    session: web.Committer, delete_form: shared.distribution.DeleteForm, project: str, version: str
) -> web.WerkzeugResponse:
    sql_platform = delete_form.platform.to_sql()  # type: ignore[attr-defined]

    # Validate the submitted data, and obtain the committee for its name
    async with db.session() as data:
        release = await data.release(name=delete_form.release_name).demand(
            RuntimeError(f"Release {delete_form.release_name} not found")
        )
        committee = release.committee
        if committee is None:
            raise RuntimeError(f"Release {delete_form.release_name} has no committee")

    # Delete the distribution
    async with storage.write_as_committee_member(committee_name=committee.name) as wacm:
        await wacm.distributions.delete_distribution(
            release_name=delete_form.release_name,
            platform=sql_platform,
            owner_namespace=delete_form.owner_namespace,
            package=delete_form.package,
            version=delete_form.version,
        )
    return await session.redirect(
        get.distribution.list_get,
        project=project,
        version=version,
        success="Distribution deleted",
    )


@post.committer("/distribution/record/<project>/<version>")
@post.form(shared.distribution.DistributeForm)
async def record_selected(
    session: web.Committer, distribute_form: shared.distribution.DistributeForm, project: str, version: str
) -> web.WerkzeugResponse:
    return await record_form_process_page(session, distribute_form, project, version, staging=False)


@post.committer("/distribution/stage/<project>/<version>")
@post.form(shared.distribution.DistributeForm)
async def stage_selected(
    session: web.Committer, distribute_form: shared.distribution.DistributeForm, project: str, version: str
) -> web.WerkzeugResponse:
    return await record_form_process_page(session, distribute_form, project, version, staging=True)


async def record_form_process_page(
    session: web.Committer,
    form_data: shared.distribution.DistributeForm,
    project: str,
    version: str,
    /,
    staging: bool = False,
) -> web.WerkzeugResponse:
    sql_platform = form_data.platform.to_sql()  # type: ignore[attr-defined]
    dd = distribution.Data(
        platform=sql_platform,
        owner_namespace=form_data.owner_namespace,
        package=form_data.package,
        version=form_data.version,
        details=form_data.details,
    )
    release, committee = await shared.distribution.release_validated_and_committee(
        project,
        version,
        staging=staging,
    )

    async with storage.write_as_committee_member(committee_name=committee.name) as w:
        try:
            _dist, added, _metadata = await w.distributions.record_from_data(
                release=release,
                staging=staging,
                dd=dd,
            )
        except storage.AccessError as e:
            # Instead of calling record_form_page_new, redirect with error message
            return await session.redirect(
                get.distribution.stage if staging else get.distribution.record,
                project=project,
                version=version,
                error=str(e),
            )

    # Success - redirect to distribution list with success message
    message = "Distribution recorded successfully." if added else "Distribution was already recorded."
    return await session.redirect(
        get.distribution.list_get,
        project=project,
        version=version,
        success=message,
    )
