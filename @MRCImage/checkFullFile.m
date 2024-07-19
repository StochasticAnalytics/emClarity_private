function is_file_the_expected_size = checkFullFile(mrc_image_obj)


    bytesPerElement = getModeBytes(mrc_image_obj);
    dimensions = getDimensions(mrc_image_obj);

    expected_size = dimensions(1) * dimensions(2) * dimensions(3) * bytesPerElement + 1024 + mrc_image_obj.header.nBytesExtended;


    is_file_the_expected_size = getFileNBytes(mrc_image_obj) == expected_size;
end