/* OHIF v3 runtime configuration for the spine-gsps viewer bench.
 *
 * Mounted over /usr/share/nginx/html/app-config.js. The container entrypoint
 * gzips whatever it finds there, because the nginx site enables gzip_static
 * always, so a bind mounted file must be writable by the container. It is
 * mounted read write for that reason.
 *
 * The data source is the bench Orthanc, reached through the same origin proxy
 * defined in default.conf.template. omitQuotationForMultipartRequest is
 * required by Orthanc's DICOMweb plugin, see the Orthanc Book chapter on OHIF.
 */
window.config = {
  routerBasename: '/',
  showStudyList: true,
  extensions: [],
  modes: [],
  showWarningMessageForCrossOrigin: false,
  showCPUFallbackMessage: false,
  investigationalUseDialog: { option: 'never' },
  defaultDataSourceName: 'dicomweb',
  dataSources: [
    {
      namespace: '@ohif/extension-default.dataSourcesModule.dicomweb',
      sourceName: 'dicomweb',
      configuration: {
        friendlyName: 'spine-gsps bench Orthanc',
        name: 'orthanc',
        wadoUriRoot: '/dicom-web',
        qidoRoot: '/dicom-web',
        wadoRoot: '/dicom-web',
        qidoSupportsIncludeField: false,
        supportsReject: false,
        imageRendering: 'wadors',
        thumbnailRendering: 'wadors',
        enableStudyLazyLoad: true,
        supportsFuzzyMatching: false,
        supportsWildcard: true,
        omitQuotationForMultipartRequest: true,
        dicomUploadEnabled: true,
        bulkDataURI: { enabled: true },
      },
    },
  ],
};
