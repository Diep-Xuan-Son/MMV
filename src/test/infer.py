from minio import Minio
import os

minio_url="localhost:9000"
minio_client = Minio(
                                endpoint=minio_url,
                                access_key="demo",
                                secret_key="demo123456",
                                secure=False,
                            )

bucket_name = "data-mmv"
collection_name = "mmv"
# minio_client.fput_object(bucket_name=bucket_name, object_name=os.path.join(collection_name, "1g3qunDMg34.mp4"), file_path='/home/mq/disk2T/son/code/GitHub/MMV/data_storage/test/1g3qunDMg34.mp4')
response = minio_client.fget_object(bucket_name=bucket_name, object_name=os.path.join(collection_name, os.path.basename("_C7beVGNYwc_splitted_0.mp4")), file_path="./_C7beVGNYwc_splitted_0.mp4")

print(response)